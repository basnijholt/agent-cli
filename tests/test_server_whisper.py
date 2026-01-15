"""Tests for the Whisper server module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.server.whisper.model_manager import (
    ModelConfig,
    ModelStats,
    TranscriptionResult,
    WhisperModelManager,
)
from agent_cli.server.whisper.model_registry import (
    WhisperModelRegistry,
)


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ModelConfig(model_name="large-v3")
        assert config.model_name == "large-v3"
        assert config.device == "auto"
        assert config.compute_type == "auto"
        assert config.ttl_seconds == 300
        assert config.cache_dir is None
        assert config.cpu_threads == 4

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
        assert stats.total_transcription_seconds == 0.0
        assert stats.last_load_time is None
        assert stats.last_request_time is None
        assert stats.load_duration_seconds is None


class TestWhisperModelManager:
    """Tests for WhisperModelManager."""

    @pytest.fixture
    def config(self) -> ModelConfig:
        """Create a test configuration."""
        return ModelConfig(
            model_name="tiny",
            device="cpu",
            compute_type="int8",
            ttl_seconds=60,
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
        assert manager._unload_task is not None

        await manager.stop()
        assert manager._shutdown is True

    @pytest.mark.asyncio
    async def test_unload_when_not_loaded(self, manager: WhisperModelManager) -> None:
        """Test unloading when model is not loaded."""
        result = await manager.unload()
        assert result is False

    @pytest.mark.asyncio
    async def test_load_model(self, manager: WhisperModelManager) -> None:
        """Test loading a model (mocked)."""
        mock_model = MagicMock()
        mock_model.model.device = "cpu"

        with patch.dict(
            "sys.modules",
            {"faster_whisper": MagicMock(WhisperModel=MagicMock(return_value=mock_model))},
        ):
            model = await manager.get_model()

        assert model is mock_model
        assert manager.is_loaded
        assert manager.stats.load_count == 1
        assert manager.stats.last_load_time is not None

    @pytest.mark.asyncio
    async def test_ttl_remaining_after_load(self, manager: WhisperModelManager) -> None:
        """Test TTL remaining calculation."""
        mock_model = MagicMock()
        mock_model.model.device = "cpu"

        with patch.dict(
            "sys.modules",
            {"faster_whisper": MagicMock(WhisperModel=MagicMock(return_value=mock_model))},
        ):
            await manager.get_model()

        ttl = manager.ttl_remaining
        assert ttl is not None
        assert 59 <= ttl <= 60  # Should be close to 60 seconds

    @pytest.mark.asyncio
    async def test_unload_after_load(self, manager: WhisperModelManager) -> None:
        """Test unloading after loading."""
        mock_model = MagicMock()
        mock_model.model.device = "cpu"

        with patch.dict(
            "sys.modules",
            {"faster_whisper": MagicMock(WhisperModel=MagicMock(return_value=mock_model))},
        ):
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
        return WhisperModelRegistry()

    @pytest.fixture
    def config(self) -> ModelConfig:
        """Create a test configuration."""
        return ModelConfig(model_name="large-v3")

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
        registry.register(ModelConfig(model_name="large-v3"))
        registry.register(ModelConfig(model_name="small"))
        registry.register(ModelConfig(model_name="tiny"))

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
        registry.register(ModelConfig(model_name="large-v3"))
        registry.register(ModelConfig(model_name="small"))

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
        registry.register(ModelConfig(model_name="large-v3"))
        registry.register(ModelConfig(model_name="small"))

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
        registry.register(ModelConfig(model_name="large-v3", ttl_seconds=300))
        registry.register(ModelConfig(model_name="small", ttl_seconds=60))

        statuses = registry.list_status()
        assert len(statuses) == 2

        large_status = next(s for s in statuses if s.name == "large-v3")
        assert large_status.loaded is False
        assert large_status.ttl_seconds == 300
        assert large_status.total_requests == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, registry: WhisperModelRegistry) -> None:
        """Test starting and stopping registry."""
        registry.register(ModelConfig(model_name="large-v3"))

        await registry.start()
        manager = registry.get_manager()
        assert manager._unload_task is not None

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
