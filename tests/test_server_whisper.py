"""Tests for the Whisper server module."""

from __future__ import annotations

import io
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.server.model_manager import ModelStats
from agent_cli.server.whisper.backends import TranscriptionResult
from agent_cli.server.whisper.model_manager import (
    WhisperModelConfig as ModelConfig,
)
from agent_cli.server.whisper.model_manager import (
    WhisperModelManager,
)
from agent_cli.server.whisper.model_registry import (
    WhisperModelRegistry,
    create_whisper_registry,
)


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values.

        Note: This only tests the ModelConfig dataclass, not model loading,
        so backend auto-detection is not triggered.
        """
        config = ModelConfig(model_name="large-v3")
        assert config.model_name == "large-v3"
        assert config.device == "auto"
        assert config.compute_type == "auto"
        assert config.ttl_seconds == 300
        assert config.cache_dir is None
        assert config.cpu_threads == 4
        assert config.backend_type == "auto"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = ModelConfig(
            model_name="small",
            device="cuda:0",
            compute_type="float16",
            ttl_seconds=600,
            cache_dir=Path("/tmp/whisper"),  # noqa: S108
            cpu_threads=8,
        )
        assert config.model_name == "small"
        assert config.device == "cuda:0"
        assert config.compute_type == "float16"
        assert config.ttl_seconds == 600
        assert config.cache_dir == Path("/tmp/whisper")  # noqa: S108
        assert config.cpu_threads == 8


class TestModelStats:
    """Tests for ModelStats dataclass."""

    def test_default_values(self) -> None:
        """Test default statistics values."""
        stats = ModelStats()
        assert stats.load_count == 0
        assert stats.unload_count == 0
        assert stats.total_requests == 0
        assert stats.total_audio_seconds == 0.0
        assert stats.extra.get("total_transcription_seconds", 0.0) == 0.0
        assert stats.last_load_time is None
        assert stats.last_request_time is None
        assert stats.load_duration_seconds is None


class TestWhisperModelManager:
    """Tests for WhisperModelManager."""

    @pytest.fixture
    def config(self) -> ModelConfig:
        """Create a test configuration.

        Uses backend_type="faster-whisper" explicitly to avoid auto-detection
        choosing mlx on macOS ARM during CI tests.
        """
        return ModelConfig(
            model_name="tiny",
            device="cpu",
            compute_type="int8",
            ttl_seconds=60,
            backend_type="faster-whisper",
        )

    @pytest.fixture
    def manager(self, config: ModelConfig) -> WhisperModelManager:
        """Create a manager instance."""
        return WhisperModelManager(config)

    def test_init(self, manager: WhisperModelManager, config: ModelConfig) -> None:
        """Test manager initialization."""
        assert manager.config == config
        assert not manager.is_loaded
        assert manager.ttl_remaining is None
        assert manager.device is None
        assert manager.stats.load_count == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, manager: WhisperModelManager) -> None:
        """Test starting and stopping the manager."""
        await manager.start()
        assert manager._manager._unload_task is not None

        await manager.stop()
        assert manager._manager._shutdown is True

    @pytest.mark.asyncio
    async def test_unload_when_not_loaded(self, manager: WhisperModelManager) -> None:
        """Test unloading when model is not loaded."""
        result = await manager.unload()
        assert result is False

    @pytest.mark.asyncio
    async def test_load_model(self, manager: WhisperModelManager) -> None:
        """Test loading a model (mocked)."""
        from agent_cli.server.whisper.backends.faster_whisper import (  # noqa: PLC0415
            FasterWhisperBackend,
        )

        async def mock_run_in_executor(
            _executor: object,
            _fn: object,
            *_args: object,
        ) -> str:
            return "cpu"

        with (
            patch.object(ProcessPoolExecutor, "__init__", lambda *_a, **_kw: None),
            patch.object(ProcessPoolExecutor, "shutdown"),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.run_in_executor = mock_run_in_executor
            backend = await manager.get_model()

        assert isinstance(backend, FasterWhisperBackend)
        assert manager.is_loaded
        assert manager.stats.load_count == 1
        assert manager.stats.last_load_time is not None

    @pytest.mark.asyncio
    async def test_ttl_remaining_after_load(self, manager: WhisperModelManager) -> None:
        """Test TTL remaining calculation."""

        async def mock_run_in_executor(
            _executor: object,
            _fn: object,
            *_args: object,
        ) -> str:
            return "cpu"

        with (
            patch.object(ProcessPoolExecutor, "__init__", lambda *_a, **_kw: None),
            patch.object(ProcessPoolExecutor, "shutdown"),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.run_in_executor = mock_run_in_executor
            await manager.get_model()

        ttl = manager.ttl_remaining
        assert ttl is not None
        assert 59 <= ttl <= 60  # Should be close to 60 seconds

    @pytest.mark.asyncio
    async def test_unload_after_load(self, manager: WhisperModelManager) -> None:
        """Test unloading after loading."""

        async def mock_run_in_executor(
            _executor: object,
            _fn: object,
            *_args: object,
        ) -> str:
            return "cpu"

        with (
            patch.object(ProcessPoolExecutor, "__init__", lambda *_a, **_kw: None),
            patch.object(ProcessPoolExecutor, "shutdown"),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.run_in_executor = mock_run_in_executor
            await manager.get_model()

            assert manager.is_loaded

            result = await manager.unload()
            assert result is True
            assert not manager.is_loaded
            assert manager.stats.unload_count == 1


class TestWhisperModelRegistry:
    """Tests for WhisperModelRegistry."""

    @pytest.fixture
    def registry(self) -> WhisperModelRegistry:
        """Create a registry instance."""
        return create_whisper_registry()

    @pytest.fixture
    def config(self) -> ModelConfig:
        """Create a test configuration.

        Uses backend_type="faster-whisper" explicitly to avoid auto-detection
        choosing mlx on macOS ARM during CI tests.
        """
        return ModelConfig(model_name="large-v3", backend_type="faster-whisper")

    def test_init(self, registry: WhisperModelRegistry) -> None:
        """Test registry initialization."""
        assert registry.default_model is None
        assert registry.models == []

    def test_register_first_model_becomes_default(
        self,
        registry: WhisperModelRegistry,
        config: ModelConfig,
    ) -> None:
        """Test that first registered model becomes default."""
        registry.register(config)
        assert registry.default_model == "large-v3"
        assert "large-v3" in registry.models

    def test_register_multiple_models(self, registry: WhisperModelRegistry) -> None:
        """Test registering multiple models."""
        registry.register(ModelConfig(model_name="large-v3", backend_type="faster-whisper"))
        registry.register(ModelConfig(model_name="small", backend_type="faster-whisper"))
        registry.register(ModelConfig(model_name="tiny", backend_type="faster-whisper"))

        assert len(registry.models) == 3
        assert "large-v3" in registry.models
        assert "small" in registry.models
        assert "tiny" in registry.models
        # First model is still default
        assert registry.default_model == "large-v3"

    def test_register_duplicate_fails(
        self,
        registry: WhisperModelRegistry,
        config: ModelConfig,
    ) -> None:
        """Test that registering duplicate model fails."""
        registry.register(config)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(config)

    def test_get_manager_default(
        self,
        registry: WhisperModelRegistry,
        config: ModelConfig,
    ) -> None:
        """Test getting manager with default model."""
        registry.register(config)
        manager = registry.get_manager()
        assert manager.config.model_name == "large-v3"

    def test_get_manager_specific(self, registry: WhisperModelRegistry) -> None:
        """Test getting manager for specific model."""
        registry.register(ModelConfig(model_name="large-v3", backend_type="faster-whisper"))
        registry.register(ModelConfig(model_name="small", backend_type="faster-whisper"))

        manager = registry.get_manager("small")
        assert manager.config.model_name == "small"

    def test_get_manager_not_found(
        self,
        registry: WhisperModelRegistry,
        config: ModelConfig,
    ) -> None:
        """Test getting manager for non-existent model."""
        registry.register(config)
        with pytest.raises(ValueError, match="not registered"):
            registry.get_manager("nonexistent")

    def test_get_manager_no_default(self, registry: WhisperModelRegistry) -> None:
        """Test getting manager with no default set."""
        with pytest.raises(ValueError, match="no default model"):
            registry.get_manager()

    def test_set_default_model(self, registry: WhisperModelRegistry) -> None:
        """Test setting default model."""
        registry.register(ModelConfig(model_name="large-v3", backend_type="faster-whisper"))
        registry.register(ModelConfig(model_name="small", backend_type="faster-whisper"))

        registry.default_model = "small"
        assert registry.default_model == "small"

    def test_set_default_model_not_registered(
        self,
        registry: WhisperModelRegistry,
        config: ModelConfig,
    ) -> None:
        """Test setting default to non-registered model."""
        registry.register(config)
        with pytest.raises(ValueError, match="not registered"):
            registry.default_model = "nonexistent"

    def test_list_status(self, registry: WhisperModelRegistry) -> None:
        """Test listing model status."""
        registry.register(
            ModelConfig(model_name="large-v3", ttl_seconds=300, backend_type="faster-whisper"),
        )
        registry.register(
            ModelConfig(model_name="small", ttl_seconds=60, backend_type="faster-whisper"),
        )

        statuses = registry.list_status()
        assert len(statuses) == 2

        large_status = next(s for s in statuses if s.name == "large-v3")
        assert large_status.loaded is False
        assert large_status.ttl_seconds == 300
        assert large_status.total_requests == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, registry: WhisperModelRegistry) -> None:
        """Test starting and stopping registry."""
        registry.register(ModelConfig(model_name="large-v3", backend_type="faster-whisper"))

        await registry.start()
        manager = registry.get_manager()
        assert manager._manager._unload_task is not None

        await registry.stop()


class TestTranscriptionResult:
    """Tests for TranscriptionResult dataclass."""

    def test_basic_result(self) -> None:
        """Test basic transcription result."""
        result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
        )
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.language_probability == 0.95
        assert result.duration == 1.5
        assert result.segments == []

    def test_result_with_segments(self) -> None:
        """Test transcription result with segments."""
        segments = [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "Hello"},
            {"id": 1, "start": 1.0, "end": 1.5, "text": "world"},
        ]
        result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=segments,
        )
        assert len(result.segments) == 2
        assert result.segments[0]["text"] == "Hello"


def _create_test_wav() -> bytes:
    """Create a minimal valid WAV file for testing."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        # Write 0.1 seconds of silence (1600 samples)
        wav_file.writeframes(b"\x00\x00" * 1600)
    buffer.seek(0)
    return buffer.read()


class TestWhisperAPI:
    """Tests for the Whisper API endpoints."""

    @pytest.fixture
    def mock_registry(self) -> WhisperModelRegistry:
        """Create a mock registry with a configured model."""
        registry = create_whisper_registry()
        registry.register(
            ModelConfig(model_name="large-v3", ttl_seconds=300, backend_type="faster-whisper"),
        )
        return registry

    @pytest.fixture
    def client(self, mock_registry: WhisperModelRegistry) -> TestClient:
        """Create a test client with mocked transcription."""
        from agent_cli.server.whisper.api import create_app  # noqa: PLC0415

        app = create_app(mock_registry, enable_wyoming=False)
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test health check endpoint returns model status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "large-v3"
        assert data["models"][0]["loaded"] is False

    def test_health_with_no_models(self) -> None:
        """Test health check with empty registry."""
        from agent_cli.server.whisper.api import create_app  # noqa: PLC0415

        registry = create_whisper_registry()
        app = create_app(registry, enable_wyoming=False)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["models"] == []

    def test_transcribe_empty_audio_returns_400(self, client: TestClient) -> None:
        """Test that empty audio file returns 400 error."""
        response = client.post(
            "/v1/audio/transcriptions",
            files={"file": ("audio.wav", b"", "audio/wav")},
            data={"model": "whisper-1"},
        )
        assert response.status_code == 400
        assert "Empty audio file" in response.json()["detail"]

    def test_transcribe_json_format(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test transcription with JSON response format."""
        mock_result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=[],
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "transcribe",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/transcriptions",
                files={"file": ("audio.wav", _create_test_wav(), "audio/wav")},
                data={"model": "whisper-1", "response_format": "json"},
            )

        assert response.status_code == 200
        assert response.json() == {"text": "Hello world"}

    def test_transcribe_text_format(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test transcription with plain text response format."""
        mock_result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=[],
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "transcribe",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/transcriptions",
                files={"file": ("audio.wav", _create_test_wav(), "audio/wav")},
                data={"model": "whisper-1", "response_format": "text"},
            )

        assert response.status_code == 200
        assert response.text == "Hello world"

    def test_transcribe_verbose_json_format(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test transcription with verbose JSON response format."""
        mock_result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=[{"id": 0, "start": 0.0, "end": 1.5, "text": "Hello world"}],
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "transcribe",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/transcriptions",
                files={"file": ("audio.wav", _create_test_wav(), "audio/wav")},
                data={"model": "whisper-1", "response_format": "verbose_json"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Hello world"
        assert data["language"] == "en"
        assert data["duration"] == 1.5
        assert data["task"] == "transcribe"
        assert len(data["segments"]) == 1

    def test_translate_endpoint(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test translation endpoint calls with translate task."""
        mock_result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=[],
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "transcribe",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_transcribe:
            response = client.post(
                "/v1/audio/translations",
                files={"file": ("audio.wav", _create_test_wav(), "audio/wav")},
                data={"model": "whisper-1"},
            )

            assert response.status_code == 200
            # Verify translate task was passed
            call_args = mock_transcribe.call_args
            assert call_args.kwargs["task"] == "translate"

    def test_unload_model_success(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test manually unloading a model."""
        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "unload",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = client.post("/v1/model/unload")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["model"] == "large-v3"
        assert data["was_loaded"] is True

    def test_unload_nonexistent_model(self, client: TestClient) -> None:
        """Test unloading a non-existent model returns 404."""
        response = client.post("/v1/model/unload?model=nonexistent")
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "chunks",
        [
            [b"\x00\x00" * 160, b"EOS"],
            [b"\x00\x00" * 160 + b"EOS"],
        ],
    )
    def test_websocket_streaming_transcription(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
        chunks: list[bytes],
    ) -> None:
        """Test WebSocket streaming endpoint returns a final transcription."""
        mock_result = TranscriptionResult(
            text="Hello world",
            language="en",
            language_probability=0.95,
            duration=1.5,
            segments=[],
        )

        manager = mock_registry.get_manager()
        with (
            patch.object(
                manager,
                "transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            client.websocket_connect(
                "/v1/audio/transcriptions/stream?model=whisper-1",
            ) as websocket,
        ):
            for chunk in chunks:
                websocket.send_bytes(chunk)
            data = websocket.receive_json()

        assert data["type"] == "final"
        assert data["text"] == "Hello world"
        assert data["is_final"] is True
        assert data["segments"] == []

    def test_websocket_streaming_unknown_model(self, client: TestClient) -> None:
        """Test WebSocket returns an error for unknown models."""
        with client.websocket_connect(
            "/v1/audio/transcriptions/stream?model=missing-model",
        ) as websocket:
            data = websocket.receive_json()

        assert data["type"] == "error"
        assert "missing-model" in data["message"]

    def test_websocket_streaming_transcribe_error(
        self,
        client: TestClient,
        mock_registry: WhisperModelRegistry,
    ) -> None:
        """Test WebSocket returns an error if transcription fails."""
        manager = mock_registry.get_manager()
        with (
            patch.object(
                manager,
                "transcribe",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            client.websocket_connect(
                "/v1/audio/transcriptions/stream?model=whisper-1",
            ) as websocket,
        ):
            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"EOS")
            data = websocket.receive_json()

        assert data["type"] == "error"
        assert data["message"] == "boom"
