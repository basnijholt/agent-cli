# Copyright (c) 2025 Bas Nijholt

"""Tests for the Wyoming Whisper server handler."""

from unittest.mock import MagicMock

import pytest
from wyoming.audio import AudioChunk

from agent_cli import constants
from agent_cli.server.whisper.wyoming_handler import WyomingWhisperHandler


@pytest.mark.asyncio
async def test_audio_chunks_are_accumulated_in_place() -> None:
    """Long streams should not copy the complete audio buffer per chunk."""
    handler = WyomingWhisperHandler(MagicMock(), MagicMock(), MagicMock())
    audio_buffer = handler._audio_bytes

    for audio in (b"first", b"second"):
        event = AudioChunk(audio=audio, **constants.WYOMING_AUDIO_CONFIG).event()
        assert await handler.handle_event(event) is True

    assert handler._audio_bytes is audio_buffer
    assert handler._audio_bytes == b"firstsecond"
