"""Extra tests for the TTS common module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._tts_common import _save_audio_file, handle_tts_playback


@pytest.mark.asyncio
@patch("agent_cli.agents._tts_common.asyncio.to_thread")
async def test_save_audio_file_os_error(mock_to_thread: AsyncMock) -> None:
    """Test _save_audio_file with OSError."""
    mock_to_thread.side_effect = OSError("Permission denied")

    await _save_audio_file(
        b"audio data",
        Path("test.wav"),
        quiet=False,
        logger=MagicMock(),
    )

    mock_to_thread.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._tts_common.tts.speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_os_error(mock_speak_text: AsyncMock) -> None:
    """Test handle_tts_playback with OSError."""
    mock_speak_text.side_effect = OSError("Connection error")
    mock_live = MagicMock()

    result = await handle_tts_playback(
        text="hello",
        tts_server_ip="localhost",
        tts_server_port=1234,
        voice_name=None,
        tts_language=None,
        speaker=None,
        output_device_index=None,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        live=mock_live,
    )

    assert result is None
