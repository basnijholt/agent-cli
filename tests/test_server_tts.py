"""Tests for the TTS server module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
        """Test that empty text returns error (422 from form validation)."""
        response = client.post(
            "/v1/audio/speech",
            data={"input": "", "model": "tts-1", "voice": "alloy"},
        )
        # Empty string in required Form field returns 422 validation error
        assert response.status_code == 422

    def test_synthesize_whitespace_text_returns_400(self, client: TestClient) -> None:
        """Test that whitespace-only text returns 400 error."""
        response = client.post(
            "/v1/audio/speech",
            data={"input": "   ", "model": "tts-1", "voice": "alloy"},
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
                data={
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
                data={
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
        """Test synthesis with JSON endpoint."""
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
                "/v1/audio/speech/json",
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
                data={
                    "input": "Hello world",
                    "model": "tts-1",
                    "voice": "alloy",
                    "speed": "1.5",
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
                data={
                    "input": "Hello world",
                    "model": "tts-1",  # OpenAI model name
                    "voice": "alloy",
                },
            )

        assert response.status_code == 200

    def test_synthesize_unsupported_format(self, client: TestClient) -> None:
        """Test that unsupported format returns 422 validation error."""
        response = client.post(
            "/v1/audio/speech/json",
            json={
                "input": "Hello world",
                "model": "tts-1",
                "voice": "alloy",
                "response_format": "unsupported",
            },
        )
        # Pydantic validation should reject invalid response_format
        assert response.status_code == 422
