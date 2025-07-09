"""Tests for the wake word detection module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.live import Live

from agent_cli.core.utils import InteractiveStopEvent
from agent_cli.services import wake_word


@pytest.fixture
def mock_pyaudio():
    """Mock PyAudio instance."""
    return MagicMock()


@pytest.fixture
def mock_logger():
    """Mock logger instance."""
    return MagicMock()


@pytest.fixture
def mock_stop_event():
    """Mock stop event."""
    stop_event = MagicMock(spec=InteractiveStopEvent)
    stop_event.is_set.return_value = False
    stop_event.ctrl_c_pressed = False
    return stop_event


@pytest.fixture
def mock_live():
    """Mock Rich Live instance."""
    return MagicMock(spec=Live)


class TestReceiveWakeDetection:
    """Tests for _receive_wake_detection function."""

    @pytest.mark.asyncio
    async def test_returns_detected_wake_word(self, mock_logger: MagicMock) -> None:
        """Test detection of wake word."""
        mock_client = AsyncMock()

        # Mock detection event
        mock_event = MagicMock()
        mock_event.type = "detection"

        # Mock Detection.is_type and Detection.from_event
        with (
            patch("agent_cli.services.wake_word.Detection.is_type", return_value=True),
            patch("agent_cli.services.wake_word.Detection.from_event") as mock_from_event,
        ):
            mock_detection = MagicMock()
            mock_detection.name = "test_wake_word"
            mock_from_event.return_value = mock_detection

            mock_client.read_event.return_value = mock_event

            result = await wake_word._receive_wake_detection(mock_client, mock_logger)

            assert result == "test_wake_word"
            mock_logger.info.assert_called_with("Wake word detected: %s", "test_wake_word")

    @pytest.mark.asyncio
    async def test_calls_detection_callback(self, mock_logger: MagicMock) -> None:
        """Test that detection callback is called."""
        mock_client = AsyncMock()
        mock_callback = MagicMock()

        # Mock detection event
        mock_event = MagicMock()
        mock_event.type = "detection"

        with (
            patch("agent_cli.services.wake_word.Detection.is_type", return_value=True),
            patch("agent_cli.services.wake_word.Detection.from_event") as mock_from_event,
        ):
            mock_detection = MagicMock()
            mock_detection.name = "test_wake_word"
            mock_from_event.return_value = mock_detection

            mock_client.read_event.return_value = mock_event

            result = await wake_word._receive_wake_detection(
                mock_client,
                mock_logger,
                detection_callback=mock_callback,
            )

            assert result == "test_wake_word"
            mock_callback.assert_called_once_with("test_wake_word")

    @pytest.mark.asyncio
    async def test_handles_not_detected_event(self, mock_logger: MagicMock) -> None:
        """Test handling of not-detected event."""
        mock_client = AsyncMock()

        # Mock not-detected event
        mock_event = MagicMock()
        mock_event.type = "not-detected"

        with (
            patch("agent_cli.services.wake_word.Detection.is_type", return_value=False),
            patch("agent_cli.services.wake_word.NotDetected.is_type", return_value=True),
        ):
            mock_client.read_event.return_value = mock_event

            result = await wake_word._receive_wake_detection(mock_client, mock_logger)

            assert result is None
            mock_logger.debug.assert_called_with("No wake word detected")

    @pytest.mark.asyncio
    async def test_handles_connection_loss(self, mock_logger: MagicMock) -> None:
        """Test handling of lost connection."""
        mock_client = AsyncMock()
        mock_client.read_event.return_value = None

        result = await wake_word._receive_wake_detection(mock_client, mock_logger)

        assert result is None
        mock_logger.warning.assert_called_with("Connection to wake word server lost.")


@pytest.mark.asyncio
@patch("agent_cli.services.wake_word.wyoming_client_context", side_effect=ConnectionRefusedError)
async def test_detect_wake_word_from_queue_connection_error(
    mock_wyoming_client_context: MagicMock,
    mock_logger: MagicMock,
    mock_live: MagicMock,
):
    """Test that detect_wake_word_from_queue handles ConnectionRefusedError."""
    result = await wake_word.detect_wake_word_from_queue(
        "localhost",
        1234,
        "test_word",
        mock_logger,
        asyncio.Queue(),
        live=mock_live,
    )
    assert result is None
    mock_wyoming_client_context.assert_called_once()
