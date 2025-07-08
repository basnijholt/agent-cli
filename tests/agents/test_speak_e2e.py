"""End-to-end tests for the speak agent with simplified mocks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.agents._config import (
    FileConfig,
    GeneralConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingTTSConfig,
)
from agent_cli.agents.speak import _async_main
from tests.mocks.audio import MockPyAudio
from tests.mocks.wyoming import MockTTSClient

if TYPE_CHECKING:
    from rich.console import Console


@pytest.mark.asyncio
@patch("agent_cli.tts.wyoming_client_context")
async def test_speak_e2e(
    mock_wyoming_client_context: MagicMock,
    mock_pyaudio_device_info: list[dict],
    mock_console: Console,
) -> None:
    """Test end-to-end speech synthesis with simplified mocks."""
    # Setup mock PyAudio
    mock_pyaudio_instance = MockPyAudio(mock_pyaudio_device_info)

    # mock the pyaudio_context in both tts and speak modules
    with (
        patch("agent_cli.tts.pyaudio_context") as mock_pyaudio_context_tts,
        patch(
            "agent_cli.agents.speak.pyaudio_context",
        ) as mock_pyaudio_context_speak,
    ):
        mock_pyaudio_context_tts.return_value.__enter__.return_value = mock_pyaudio_instance
        mock_pyaudio_context_speak.return_value.__enter__.return_value = mock_pyaudio_instance

        # Setup mock Wyoming client
        mock_tts_client = MockTTSClient(b"fake audio data")
        mock_wyoming_client_context.return_value.__aenter__.return_value = mock_tts_client

        general_cfg = GeneralConfig(
            log_level="INFO",
            log_file=None,
            list_devices=False,
            quiet=False,
            clipboard=False,
        )
        general_cfg.__dict__["console"] = mock_console
        tts_config = TTSConfig(
            enabled=True,
            provider="local",
            output_device_index=None,
            output_device_name=None,
            speed=1.0,
            local=WyomingTTSConfig(
                server_ip="mock-host",
                server_port=10200,
                voice_name=None,
                language=None,
                speaker=None,
            ),
            openai=OpenAITTSConfig(api_key=None),
        )
        file_config = FileConfig(save_file=None, history_dir=None, last_n_messages=0)

        await _async_main(
            general_cfg=general_cfg,
            text="Hello, world!",
            tts_config=tts_config,
            file_config=file_config,
        )

    # Verify that the audio was "played"
    mock_wyoming_client_context.assert_called_once()
    assert mock_pyaudio_instance.streams[0].get_written_data()
