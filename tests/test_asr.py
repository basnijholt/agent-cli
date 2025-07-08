"""Unit tests for the asr module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from wyoming.asr import Transcribe, Transcript, TranscriptChunk
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import asr


@pytest.mark.asyncio
async def test_send_audio() -> None:
    """Test that _send_audio sends the correct events."""
    # Arrange
    client = AsyncMock()
    stream = MagicMock()
    stop_event = MagicMock()
    stop_event.is_set.side_effect = [False, True]  # Allow one iteration then stop
    stop_event.ctrl_c_pressed = False

    stream.read.return_value = b"fake_audio_chunk"
    logger = MagicMock()

    # Act
    # No need to create a task and sleep, just await the coroutine.
    # The side_effect will stop the loop.
    await asr._send_audio(client, stream, stop_event, logger, live=MagicMock(), quiet=False)

    # Assert
    assert client.write_event.call_count == 4
    client.write_event.assert_any_call(Transcribe().event())
    client.write_event.assert_any_call(
        AudioStart(rate=16000, width=2, channels=1).event(),
    )
    client.write_event.assert_any_call(
        AudioChunk(
            rate=16000,
            width=2,
            channels=1,
            audio=b"fake_audio_chunk",
        ).event(),
    )
    client.write_event.assert_any_call(AudioStop().event())


@pytest.mark.asyncio
async def test_receive_text() -> None:
    """Test that receive_transcript correctly processes events."""
    # Arrange
    client = AsyncMock()
    client.read_event.side_effect = [
        TranscriptChunk(text="hello").event(),
        Transcript(text="hello world").event(),
        None,  # To stop the loop
    ]
    logger = MagicMock()
    chunk_callback = MagicMock()
    final_callback = MagicMock()

    # Act
    result = await asr._receive_transcript(
        client,
        logger,
        chunk_callback=chunk_callback,
        final_callback=final_callback,
    )

    # Assert
    assert result == "hello world"
    chunk_callback.assert_called_once_with("hello")
    final_callback.assert_called_once_with("hello world")
