"""Tests for the wake word assistant agent."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents.wake_word_assistant import _record_audio_with_wake_word


@pytest.fixture
def mock_pyaudio() -> MagicMock:
    """Mock PyAudio instance."""
    return MagicMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    """Mock logger instance."""
    return MagicMock()


@pytest.fixture
def mock_stop_event() -> MagicMock:
    """Mock stop event."""
    stop_event = MagicMock()
    stop_event.is_set.return_value = False
    return stop_event


@pytest.fixture
def mock_live() -> MagicMock:
    """Mock Rich Live instance."""
    return MagicMock()


@pytest.fixture
def mock_wake_word_config() -> MagicMock:
    """Mock WakeWordConfig."""
    config = MagicMock()
    config.wake_word_name = "test_word"
    config.server_ip = "127.0.0.1"
    config.server_port = 10400
    return config


class TestRecordAudioWithWakeWord:
    """Tests for _record_audio_with_wake_word function."""

    @pytest.mark.asyncio
    @patch("agent_cli.agents.wake_word_assistant.wake_word.detect_wake_word_from_queue")
    @patch("agent_cli.agents.wake_word_assistant.wake_word.detect_wake_word")
    @patch("agent_cli.agents.wake_word_assistant.asr.record_audio_to_buffer")
    @patch("agent_cli.agents.wake_word_assistant.audio.tee_audio_stream")
    async def test_full_recording_cycle(
        self,
        mock_tee: MagicMock,
        mock_record_buffer: AsyncMock,
        mock_detect: AsyncMock,
        mock_detect_from_queue: AsyncMock,
        mock_pyaudio: MagicMock,
        mock_logger: MagicMock,
        mock_stop_event: MagicMock,
        mock_wake_word_config: MagicMock,
        mock_live: MagicMock,
    ) -> None:
        """Test a full recording cycle from start to stop wake word."""
        # Arrange
        mock_detect.return_value = "start_word"
        mock_detect_from_queue.return_value = "stop_word"
        mock_record_buffer.return_value = b"test_audio"

        # Mock the tee context manager and the yielded tee object
        mock_tee_instance = MagicMock()
        mock_tee_instance.stop = AsyncMock()
        mock_tee_instance.add_queue.return_value = asyncio.Queue()
        mock_tee.return_value.__aenter__.return_value = mock_tee_instance

        # Act
        result = await _record_audio_with_wake_word(
            p=mock_pyaudio,
            input_device_index=1,
            stop_event=mock_stop_event,
            logger=mock_logger,
            wake_word_config=mock_wake_word_config,
            quiet=False,
            live=mock_live,
        )

        # Assert
        assert result == b"test_audio"
        mock_detect.assert_called_once()
        mock_detect_from_queue.assert_called_once()
        mock_record_buffer.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_cli.agents.wake_word_assistant.wake_word.detect_wake_word")
    async def test_no_start_word_detected(
        self,
        mock_detect: AsyncMock,
        mock_pyaudio: MagicMock,
        mock_logger: MagicMock,
        mock_stop_event: MagicMock,
        mock_wake_word_config: MagicMock,
        mock_live: MagicMock,
    ) -> None:
        """Test that None is returned if no start word is detected."""
        # Arrange
        mock_detect.return_value = None

        # Act
        result = await _record_audio_with_wake_word(
            p=mock_pyaudio,
            input_device_index=1,
            stop_event=mock_stop_event,
            logger=mock_logger,
            wake_word_config=mock_wake_word_config,
            quiet=True,
            live=mock_live,
        )

        # Assert
        assert result is None
        mock_detect.assert_called_once()

    @pytest.mark.asyncio
    @patch("agent_cli.agents.wake_word_assistant.wake_word.detect_wake_word_from_queue")
    @patch("agent_cli.agents.wake_word_assistant.wake_word.detect_wake_word")
    @patch("agent_cli.agents.wake_word_assistant.asr.record_audio_to_buffer")
    @patch("agent_cli.agents.wake_word_assistant.audio.tee_audio_stream")
    async def test_no_stop_word_detected(
        self,
        mock_tee: MagicMock,
        mock_record_buffer: AsyncMock,
        mock_detect: AsyncMock,
        mock_detect_from_queue: AsyncMock,
        mock_pyaudio: MagicMock,
        mock_logger: MagicMock,
        mock_stop_event: MagicMock,
        mock_wake_word_config: MagicMock,
        mock_live: MagicMock,
    ) -> None:
        """Test that None is returned if no stop word is detected."""
        # Arrange
        mock_detect.return_value = "start_word"
        mock_detect_from_queue.return_value = None
        mock_record_buffer.return_value = b"test_audio"

        # Mock the tee context manager and the yielded tee object
        mock_tee_instance = MagicMock()
        mock_tee_instance.stop = AsyncMock()
        mock_tee_instance.add_queue.return_value = asyncio.Queue()
        mock_tee.return_value.__aenter__.return_value = mock_tee_instance

        # Act
        result = await _record_audio_with_wake_word(
            p=mock_pyaudio,
            input_device_index=1,
            stop_event=mock_stop_event,
            logger=mock_logger,
            wake_word_config=mock_wake_word_config,
            quiet=True,
            live=mock_live,
        )

        # Assert
        assert result is None
        mock_detect.assert_called_once()
        mock_detect_from_queue.assert_called_once()


# Integration-style tests for the CLI command would go here,
# but they are complex to set up and mock.
# The unit tests above cover the core logic of the agent.
