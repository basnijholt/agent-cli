"""Tests for the TTS common module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._tts_common import handle_tts_playback

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@patch("agent_cli.agents._tts_common.tts.speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback(mock_speak_text: AsyncMock) -> None:
    """Test the handle_tts_playback function."""
    mock_speak_text.return_value = b"audio data"
    mock_live = MagicMock()
    await handle_tts_playback(
        text="hello",
        service_provider="local",
        openai_api_key=None,
        tts_server_ip="localhost",
        tts_server_port=1234,
        voice_name="test-voice",
        tts_language="en",
        speaker=None,
        output_device_index=1,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        speed=1.0,
        live=mock_live,
    )

    mock_speak_text.assert_called_once_with(
        text="hello",
        service_provider="local",
        openai_api_key=None,
        tts_server_ip="localhost",
        tts_server_port=1234,
        logger=mock_speak_text.call_args.kwargs["logger"],
        voice_name="test-voice",
        language="en",
        speaker=None,
        output_device_index=1,
        quiet=False,
        play_audio_flag=True,
        stop_event=None,
        speed=1.0,
        live=mock_live,
    )


@pytest.mark.asyncio
@patch("agent_cli.agents._tts_common.tts.speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_with_save_file(
    mock_speak_text: AsyncMock,
    tmp_path: Path,
) -> None:
    """Test the handle_tts_playback function with file saving."""
    mock_speak_text.return_value = b"audio data"
    save_file = tmp_path / "test.wav"
    mock_live = MagicMock()

    await handle_tts_playback(
        text="hello",
        service_provider="local",
        openai_api_key=None,
        tts_server_ip="localhost",
        tts_server_port=1234,
        voice_name="test-voice",
        tts_language="en",
        speaker=None,
        output_device_index=1,
        save_file=save_file,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        speed=1.0,
        live=mock_live,
    )

    # Verify the file was saved
    assert save_file.exists()
    assert save_file.read_bytes() == b"audio data"


@pytest.mark.asyncio
@patch("agent_cli.agents._tts_common.tts.speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_no_audio(mock_speak_text: AsyncMock) -> None:
    """Test the handle_tts_playback function when no audio is returned."""
    mock_speak_text.return_value = None
    mock_live = MagicMock()
    await handle_tts_playback(
        text="hello",
        service_provider="local",
        openai_api_key=None,
        tts_server_ip="localhost",
        tts_server_port=1234,
        voice_name="test-voice",
        tts_language="en",
        speaker=None,
        output_device_index=1,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        speed=1.0,
        live=mock_live,
    )

    mock_speak_text.assert_called_once()
