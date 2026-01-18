"""Tests for the TTS server module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.server.model_manager import ModelStats
from agent_cli.server.tts.backends import SynthesisResult
from agent_cli.server.tts.model_manager import TTSModelConfig, TTSModelManager
from agent_cli.server.tts.model_registry import TTSModelRegistry, create_tts_registry


class TestTTSModelConfig:
    """Tests for TTSModelConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = TTSModelConfig(model_name="en_US-lessac-medium")
        assert config.model_name == "en_US-lessac-medium"
        assert config.device == "auto"
        assert config.ttl_seconds == 300
        assert config.cache_dir is None
        assert config.backend_type == "auto"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = TTSModelConfig(
            model_name="en_GB-alan-medium",
            device="cpu",
            ttl_seconds=600,
            cache_dir=Path("/tmp/piper"),  # noqa: S108
            backend_type="piper",
        )
        assert config.model_name == "en_GB-alan-medium"
        assert config.device == "cpu"
        assert config.ttl_seconds == 600
        assert config.cache_dir == Path("/tmp/piper")  # noqa: S108
        assert config.backend_type == "piper"

    def test_kokoro_backend_type(self) -> None:
        """Test Kokoro backend configuration."""
        config = TTSModelConfig(
            model_name="/path/to/kokoro-v1_0.pth",
            device="cuda",
            ttl_seconds=300,
            cache_dir=Path("/tmp/kokoro"),  # noqa: S108
            backend_type="kokoro",
        )
        assert config.model_name == "/path/to/kokoro-v1_0.pth"
        assert config.device == "cuda"
        assert config.backend_type == "kokoro"


class TestModelStats:
    """Tests for ModelStats dataclass with TTS-specific fields."""

    def test_default_values(self) -> None:
        """Test default statistics values."""
        stats = ModelStats()
        assert stats.load_count == 0
        assert stats.unload_count == 0
        assert stats.total_requests == 0
        assert stats.total_audio_seconds == 0.0
        assert stats.extra.get("total_characters", 0.0) == 0.0
        assert stats.extra.get("total_synthesis_seconds", 0.0) == 0.0
        assert stats.last_load_time is None
        assert stats.last_request_time is None
        assert stats.load_duration_seconds is None


class TestTTSModelManager:
    """Tests for TTSModelManager."""

    @pytest.fixture
    def config(self) -> TTSModelConfig:
        """Create a test configuration."""
        return TTSModelConfig(
            model_name="en_US-lessac-medium",
            device="cpu",
            ttl_seconds=60,
            backend_type="piper",
        )

    @pytest.fixture
    def manager(self, config: TTSModelConfig) -> TTSModelManager:
        """Create a manager instance with mocked backend."""
        with patch(
            "agent_cli.server.tts.model_manager.create_backend",
        ) as mock_create_backend:
            mock_backend = MagicMock()
            mock_backend.is_loaded = False
            mock_backend.device = None
            mock_create_backend.return_value = mock_backend
            return TTSModelManager(config)

    def test_init(self, manager: TTSModelManager, config: TTSModelConfig) -> None:
        """Test manager initialization."""
        assert manager.config == config
        assert not manager.is_loaded
        assert manager.ttl_remaining is None
        assert manager.device is None
        assert manager.stats.load_count == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, manager: TTSModelManager) -> None:
        """Test starting and stopping the manager."""
        await manager.start()
        assert manager._manager._unload_task is not None

        await manager.stop()
        assert manager._manager._shutdown is True

    @pytest.mark.asyncio
    async def test_unload_when_not_loaded(self, manager: TTSModelManager) -> None:
        """Test unloading when model is not loaded."""
        result = await manager.unload()
        assert result is False


class TestTTSModelRegistry:
    """Tests for TTSModelRegistry."""

    @pytest.fixture
    def registry(self) -> TTSModelRegistry:
        """Create a registry instance."""
        return create_tts_registry()

    @pytest.fixture
    def config(self) -> TTSModelConfig:
        """Create a test configuration."""
        return TTSModelConfig(
            model_name="en_US-lessac-medium",
            ttl_seconds=300,
            backend_type="piper",
        )

    def test_init(self, registry: TTSModelRegistry) -> None:
        """Test registry initialization."""
        assert registry.default_model is None
        assert registry.models == []

    def test_register_first_model_becomes_default(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test that first registered model becomes default."""
        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config)

        assert registry.default_model == "en_US-lessac-medium"
        assert registry.models == ["en_US-lessac-medium"]

    def test_register_multiple_models(self, registry: TTSModelRegistry) -> None:
        """Test registering multiple models."""
        config1 = TTSModelConfig(model_name="en_US-lessac-medium", backend_type="piper")
        config2 = TTSModelConfig(model_name="en_GB-alan-medium", backend_type="piper")

        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config1)
            registry.register(config2)

        assert registry.default_model == "en_US-lessac-medium"
        assert set(registry.models) == {"en_US-lessac-medium", "en_GB-alan-medium"}

    def test_register_duplicate_fails(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test that registering duplicate model raises error."""
        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config)
            with pytest.raises(ValueError, match="already registered"):
                registry.register(config)

    def test_get_manager_default(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test getting default manager."""
        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config)
            manager = registry.get_manager()

        assert manager.config.model_name == "en_US-lessac-medium"

    def test_get_manager_specific(self, registry: TTSModelRegistry) -> None:
        """Test getting specific model manager."""
        config1 = TTSModelConfig(model_name="en_US-lessac-medium", backend_type="piper")
        config2 = TTSModelConfig(model_name="en_GB-alan-medium", backend_type="piper")

        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config1)
            registry.register(config2)
            manager = registry.get_manager("en_GB-alan-medium")

        assert manager.config.model_name == "en_GB-alan-medium"

    def test_get_manager_not_found(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test getting non-existent model raises error."""
        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config)
            with pytest.raises(ValueError, match="not registered"):
                registry.get_manager("nonexistent")

    def test_get_manager_no_default(self, registry: TTSModelRegistry) -> None:
        """Test getting manager with no default set raises error."""
        with pytest.raises(ValueError, match="No model specified"):
            registry.get_manager()

    def test_set_default_model(
        self,
        registry: TTSModelRegistry,
    ) -> None:
        """Test setting default model."""
        config1 = TTSModelConfig(model_name="en_US-lessac-medium", backend_type="piper")
        config2 = TTSModelConfig(model_name="en_GB-alan-medium", backend_type="piper")

        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config1)
            registry.register(config2)

        assert registry.default_model == "en_US-lessac-medium"
        registry.default_model = "en_GB-alan-medium"
        assert registry.default_model == "en_GB-alan-medium"

    def test_set_default_model_not_registered(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test setting non-existent default model raises error."""
        with patch("agent_cli.server.tts.model_manager.create_backend"):
            registry.register(config)
            with pytest.raises(ValueError, match="not registered"):
                registry.default_model = "nonexistent"

    def test_list_status(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test listing model status."""
        with patch("agent_cli.server.tts.model_manager.create_backend") as mock:
            mock_backend = MagicMock()
            mock_backend.is_loaded = False
            mock_backend.device = None
            mock.return_value = mock_backend
            registry.register(config)

        statuses = registry.list_status()
        assert len(statuses) == 1
        assert statuses[0].name == "en_US-lessac-medium"
        assert statuses[0].loaded is False

    @pytest.mark.asyncio
    async def test_start_stop(
        self,
        registry: TTSModelRegistry,
        config: TTSModelConfig,
    ) -> None:
        """Test starting and stopping registry."""
        with patch("agent_cli.server.tts.model_manager.create_backend") as mock:
            mock_backend = MagicMock()
            mock_backend.is_loaded = False
            mock_backend.device = None
            mock.return_value = mock_backend
            registry.register(config)

        await registry.start()
        manager = registry.get_manager()
        assert manager._manager._unload_task is not None

        await registry.stop()


class TestSynthesisResult:
    """Tests for SynthesisResult dataclass."""

    def test_basic_result(self) -> None:
        """Test creating a basic synthesis result."""
        result = SynthesisResult(
            audio=b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )
        assert result.audio == b"\x00\x00" * 1000
        assert result.sample_rate == 22050
        assert result.sample_width == 2
        assert result.channels == 1
        assert result.duration == 1.5


class TestBackendFactory:
    """Tests for the TTS backend factory."""

    def test_create_piper_backend(self) -> None:
        """Test creating a Piper backend."""
        from agent_cli.server.tts.backends import BackendConfig, create_backend  # noqa: PLC0415

        with patch(
            "agent_cli.server.tts.backends.piper.PiperBackend.__init__",
            return_value=None,
        ):
            backend = create_backend(
                BackendConfig(model_name="en_US-lessac-medium"),
                backend_type="piper",
            )
            assert backend.__class__.__name__ == "PiperBackend"

    def test_create_kokoro_backend(self) -> None:
        """Test creating a Kokoro backend."""
        from agent_cli.server.tts.backends import BackendConfig, create_backend  # noqa: PLC0415

        with patch(
            "agent_cli.server.tts.backends.kokoro.KokoroBackend.__init__",
            return_value=None,
        ):
            backend = create_backend(
                BackendConfig(model_name="/path/to/kokoro.pth"),
                backend_type="kokoro",
            )
            assert backend.__class__.__name__ == "KokoroBackend"

    def test_create_unknown_backend_raises(self) -> None:
        """Test that unknown backend type raises ValueError."""
        from agent_cli.server.tts.backends import BackendConfig, create_backend  # noqa: PLC0415

        with pytest.raises(ValueError, match="Unknown backend type"):
            create_backend(
                BackendConfig(model_name="test"),
                backend_type="unknown",  # type: ignore[arg-type]
            )


class TestKokoroBackend:
    """Tests for the Kokoro TTS backend."""

    def test_default_voice(self) -> None:
        """Test default voice is set correctly."""
        from agent_cli.server.tts.backends.kokoro import DEFAULT_VOICE  # noqa: PLC0415

        assert DEFAULT_VOICE == "af_heart"

    def test_kokoro_hf_repo(self) -> None:
        """Test Kokoro HuggingFace repo constant."""
        from agent_cli.server.tts.backends.kokoro import KOKORO_HF_REPO  # noqa: PLC0415

        assert KOKORO_HF_REPO == "hexgrad/Kokoro-82M"

    def test_backend_init(self) -> None:
        """Test KokoroBackend initialization."""
        from agent_cli.server.tts.backends import BackendConfig  # noqa: PLC0415
        from agent_cli.server.tts.backends.kokoro import KokoroBackend  # noqa: PLC0415

        config = BackendConfig(model_name="kokoro", cache_dir=Path("/tmp/test"))  # noqa: S108
        backend = KokoroBackend(config)

        assert backend.is_loaded is False
        assert backend.device is None
        assert backend._cache_dir == Path("/tmp/test")  # noqa: S108

    def test_resolve_model_path_auto(self, tmp_path: Path) -> None:
        """Test model path resolution with auto/kokoro triggers download."""
        from agent_cli.server.tts.backends.kokoro import _resolve_model_path  # noqa: PLC0415

        with patch(
            "agent_cli.server.tts.backends.kokoro._ensure_model",
        ) as mock_ensure:
            mock_ensure.return_value = Path("/cache/model/kokoro-v1_0.pth")
            result = _resolve_model_path("kokoro", tmp_path)

        mock_ensure.assert_called_once_with(tmp_path)
        assert result == Path("/cache/model/kokoro-v1_0.pth")

    def test_resolve_model_path_explicit(self, tmp_path: Path) -> None:
        """Test model path resolution with explicit path."""
        from agent_cli.server.tts.backends.kokoro import _resolve_model_path  # noqa: PLC0415

        # Create a fake model file
        model_file = tmp_path / "model.pth"
        model_file.touch()

        result = _resolve_model_path(str(model_file), tmp_path)
        assert result == model_file

    def test_resolve_voice_path_triggers_download(self, tmp_path: Path) -> None:
        """Test voice path resolution triggers download when not cached."""
        from agent_cli.server.tts.backends.kokoro import _resolve_voice_path  # noqa: PLC0415

        with patch(
            "agent_cli.server.tts.backends.kokoro._ensure_voice",
        ) as mock_ensure:
            voice_path = tmp_path / "voices" / "af_bella.pt"
            mock_ensure.return_value = voice_path
            _path, lang_code = _resolve_voice_path("af_bella", tmp_path)

        mock_ensure.assert_called_once_with("af_bella", tmp_path)
        assert lang_code == "a"

    def test_resolve_voice_path_cached(self, tmp_path: Path) -> None:
        """Test voice path resolution when voice is already cached."""
        from agent_cli.server.tts.backends.kokoro import _resolve_voice_path  # noqa: PLC0415

        # Create cached voice file
        voices_dir = tmp_path / "voices"
        voices_dir.mkdir()
        voice_file = voices_dir / "af_heart.pt"
        voice_file.touch()

        path, lang_code = _resolve_voice_path("af_heart", tmp_path)

        assert path == str(voice_file)
        assert lang_code == "a"

    def test_resolve_voice_path_explicit_file(self, tmp_path: Path) -> None:
        """Test voice path resolution with explicit file path."""
        from agent_cli.server.tts.backends.kokoro import _resolve_voice_path  # noqa: PLC0415

        # Create explicit voice file
        voice_file = tmp_path / "custom_voice.pt"
        voice_file.touch()

        path, lang_code = _resolve_voice_path(str(voice_file), tmp_path)

        assert path == str(voice_file)
        assert lang_code == "c"  # First letter of "custom_voice"

    def test_resolve_voice_path_default(self, tmp_path: Path) -> None:
        """Test voice path resolution uses default voice when None."""
        from agent_cli.server.tts.backends.kokoro import (  # noqa: PLC0415
            DEFAULT_VOICE,
            _resolve_voice_path,
        )

        with patch(
            "agent_cli.server.tts.backends.kokoro._ensure_voice",
        ) as mock_ensure:
            voice_path = tmp_path / "voices" / f"{DEFAULT_VOICE}.pt"
            mock_ensure.return_value = voice_path
            _resolve_voice_path(None, tmp_path)

        mock_ensure.assert_called_once_with(DEFAULT_VOICE, tmp_path)


class TestTTSAPI:
    """Tests for the TTS API endpoints."""

    @pytest.fixture
    def mock_registry(self) -> TTSModelRegistry:
        """Create a mock registry with a configured model."""
        registry = create_tts_registry()
        with patch("agent_cli.server.tts.model_manager.create_backend") as mock:
            mock_backend = MagicMock()
            mock_backend.is_loaded = False
            mock_backend.device = None
            mock.return_value = mock_backend
            registry.register(
                TTSModelConfig(
                    model_name="en_US-lessac-medium",
                    ttl_seconds=300,
                    backend_type="piper",
                ),
            )
        return registry

    @pytest.fixture
    def client(self, mock_registry: TTSModelRegistry) -> TestClient:
        """Create a test client with mocked synthesis."""
        from agent_cli.server.tts.api import create_app  # noqa: PLC0415

        app = create_app(mock_registry, enable_wyoming=False)
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test health check endpoint returns model status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "en_US-lessac-medium"
        assert data["models"][0]["loaded"] is False

    def test_health_with_no_models(self) -> None:
        """Test health check with empty registry."""
        from agent_cli.server.tts.api import create_app  # noqa: PLC0415

        registry = create_tts_registry()
        app = create_app(registry, enable_wyoming=False)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["models"] == []

    def test_voices_endpoint(self, client: TestClient) -> None:
        """Test voices endpoint returns available voices."""
        response = client.get("/v1/voices")
        assert response.status_code == 200
        data = response.json()
        assert len(data["voices"]) == 1
        assert data["voices"][0]["voice_id"] == "en_US-lessac-medium"
        assert data["voices"][0]["name"] == "en_US-lessac-medium"
        assert "Piper TTS" in data["voices"][0]["description"]

    def test_voices_with_no_models(self) -> None:
        """Test voices endpoint with empty registry."""
        from agent_cli.server.tts.api import create_app  # noqa: PLC0415

        registry = create_tts_registry()
        app = create_app(registry, enable_wyoming=False)
        client = TestClient(app)

        response = client.get("/v1/voices")
        assert response.status_code == 200
        data = response.json()
        assert data["voices"] == []

    def test_synthesize_empty_text_returns_error(self, client: TestClient) -> None:
        """Test that empty text returns 400 error."""
        response = client.post(
            "/v1/audio/speech",
            json={"input": "", "model": "tts-1", "voice": "alloy"},
        )
        # Empty string returns 400 from our validation
        assert response.status_code == 400

    def test_synthesize_whitespace_text_returns_400(self, client: TestClient) -> None:
        """Test that whitespace-only text returns 400 error."""
        response = client.post(
            "/v1/audio/speech",
            json={"input": "   ", "model": "tts-1", "voice": "alloy"},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_synthesize_wav_format(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test synthesis with WAV response format."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,  # Fake WAV
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "synthesize",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "wav",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"

    def test_synthesize_pcm_format(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test synthesis with PCM response format."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,  # Fake WAV
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "synthesize",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "pcm",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/pcm"
        assert "x-sample-rate" in response.headers
        assert "x-sample-width" in response.headers
        assert "x-channels" in response.headers

    def test_synthesize_json_endpoint(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test synthesis with JSON body (OpenAI-compatible)."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "synthesize",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "wav",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"

    def test_synthesize_with_speed(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test synthesis with speed parameter."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.0,  # Faster due to speed=1.5
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "synthesize",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_synthesize:
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "speed": 1.5,
                    "response_format": "wav",  # Use WAV to avoid FFmpeg dependency
                },
            )

        assert response.status_code == 200
        mock_synthesize.assert_called_once()
        call_kwargs = mock_synthesize.call_args[1]
        assert call_kwargs["speed"] == 1.5

    def test_unload_model_success(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test unloading a model successfully."""
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
        assert data["model"] == "en_US-lessac-medium"
        assert data["was_loaded"] is True

    def test_unload_nonexistent_model(self, client: TestClient) -> None:
        """Test unloading a non-existent model returns 404."""
        response = client.post("/v1/model/unload?model=nonexistent")
        assert response.status_code == 404
        assert "not registered" in response.json()["detail"]

    def test_synthesize_uses_default_model_for_tts1(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that tts-1 model name uses the default model."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with patch.object(
            manager,
            "synthesize",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",  # OpenAI model name
                    "voice": "alloy",
                    "response_format": "wav",  # Use WAV to avoid FFmpeg dependency
                },
            )

        assert response.status_code == 200

    def test_synthesize_uses_mp3_as_default_format(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that mp3 is the default response_format (OpenAI compatibility)."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with (
            patch.object(
                manager,
                "synthesize",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "agent_cli.server.tts.api.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "agent_cli.server.tts.api.convert_to_mp3",
                return_value=b"fake mp3 data",
            ),
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    # No response_format specified - should default to mp3
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"

    def test_synthesize_unsupported_format(self, client: TestClient) -> None:
        """Test that unsupported format returns 422 validation error."""
        response = client.post(
            "/v1/audio/speech",
            json={
                "input": "Hello world",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "unsupported",
            },
        )
        # Pydantic validation should reject invalid response_format
        assert response.status_code == 422

    def test_synthesize_mp3_format_no_ffmpeg(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that MP3 format returns 422 when ffmpeg is not available."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with (
            patch.object(
                manager,
                "synthesize",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "agent_cli.server.tts.api.check_ffmpeg_available",
                return_value=False,
            ),
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "mp3",
                },
            )

        assert response.status_code == 422
        assert "ffmpeg" in response.json()["detail"].lower()

    def test_synthesize_mp3_format_with_ffmpeg(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that MP3 format works when ffmpeg is available."""
        mock_result = SynthesisResult(
            audio=b"RIFF" + b"\x00" * 40 + b"\x00\x00" * 1000,
            sample_rate=22050,
            sample_width=2,
            channels=1,
            duration=1.5,
        )

        manager = mock_registry.get_manager()
        with (
            patch.object(
                manager,
                "synthesize",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "agent_cli.server.tts.api.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "agent_cli.server.tts.api.convert_to_mp3",
                return_value=b"fake mp3 data",
            ),
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "mp3",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"

    def test_stream_format_empty_text_returns_error(self, client: TestClient) -> None:
        """Test that empty text returns 400 for stream_format=audio."""
        response = client.post(
            "/v1/audio/speech",
            json={
                "input": "",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "pcm",
                "stream_format": "audio",
            },
        )
        assert response.status_code == 400

    def test_stream_format_whitespace_text_returns_400(
        self,
        client: TestClient,
    ) -> None:
        """Test that whitespace-only text returns 400 for stream_format=audio."""
        response = client.post(
            "/v1/audio/speech",
            json={
                "input": "   ",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "pcm",
                "stream_format": "audio",
            },
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_stream_format_unsupported_backend(
        self,
        client: TestClient,
    ) -> None:
        """Test that streaming with unsupported backend returns 422."""
        with patch.object(
            TTSModelManager,
            "supports_streaming",
            new_callable=PropertyMock,
            return_value=False,
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "pcm",
                    "stream_format": "audio",
                },
            )

        assert response.status_code == 422
        assert "streaming" in response.json()["detail"].lower()

    def test_stream_format_invalid_value(self, client: TestClient) -> None:
        """Test that invalid stream_format value returns 422."""
        response = client.post(
            "/v1/audio/speech",
            json={
                "input": "Hello world",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "pcm",
                "stream_format": "invalid",
            },
        )
        assert response.status_code == 422

    def test_stream_format_requires_pcm(self, client: TestClient) -> None:
        """Test that streaming requires response_format=pcm."""
        response = client.post(
            "/v1/audio/speech",
            json={
                "input": "Hello world",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "wav",
                "stream_format": "audio",
            },
        )
        assert response.status_code == 422
        assert "pcm" in response.json()["detail"].lower()

    def test_stream_format_returns_pcm_headers(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that stream_format=audio returns correct PCM headers."""
        from collections.abc import AsyncIterator  # noqa: PLC0415, TC003

        async def mock_stream(
            *_args: object,
            **_kwargs: object,
        ) -> AsyncIterator[bytes]:
            yield b"\x00\x00" * 100

        manager = mock_registry.get_manager()
        with (
            patch.object(
                TTSModelManager,
                "supports_streaming",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(manager, "synthesize_stream", mock_stream),
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "pcm",
                    "stream_format": "audio",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/pcm"
        assert response.headers["x-sample-rate"] == "24000"
        assert response.headers["x-sample-width"] == "2"
        assert response.headers["x-channels"] == "1"

    def test_stream_format_returns_audio_chunks(
        self,
        client: TestClient,
        mock_registry: TTSModelRegistry,
    ) -> None:
        """Test that stream_format=audio returns audio data."""
        from collections.abc import AsyncIterator  # noqa: PLC0415, TC003

        expected_data = b"\x00\x01" * 100 + b"\x02\x03" * 100

        async def mock_stream(
            *_args: object,
            **_kwargs: object,
        ) -> AsyncIterator[bytes]:
            yield b"\x00\x01" * 100
            yield b"\x02\x03" * 100

        manager = mock_registry.get_manager()
        with (
            patch.object(
                TTSModelManager,
                "supports_streaming",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(manager, "synthesize_stream", mock_stream),
        ):
            response = client.post(
                "/v1/audio/speech",
                json={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "response_format": "pcm",
                    "stream_format": "audio",
                },
            )

        assert response.status_code == 200
        assert response.content == expected_data
