"""End-to-end tests for the speak agent with simplified mocks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents.speak import _async_main
from tests.mocks.audio import MockPyAudio
from tests.mocks.wyoming import MockTTSClient


@pytest.mark.asyncio
@patch("agent_cli.services.tts.wyoming_client_context")
async def test_speak_e2e(
    mock_wyoming_client_context: MagicMock,
    mock_pyaudio_device_info: list[dict],
) -> None:
    """Test end-to-end speech synthesis with simplified mocks."""
    # Setup mock PyAudio
    mock_pyaudio_instance = MockPyAudio(mock_pyaudio_device_info)

    # mock the pyaudio_context in both tts and speak modules
    with (
        patch("agent_cli.services.tts.pyaudio_context") as mock_pyaudio_context_tts,
        patch(
            "agent_cli.agents.speak.pyaudio_context",
        ) as mock_pyaudio_context_speak,
    ):
        mock_pyaudio_context_tts.return_value.__enter__.return_value = mock_pyaudio_instance
        mock_pyaudio_context_speak.return_value.__enter__.return_value = mock_pyaudio_instance

        # Setup mock Wyoming client
        mock_tts_client = MockTTSClient(b"fake audio data")
        mock_wyoming_client_context.return_value.__aenter__.return_value = mock_tts_client

        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            list_devices=False,
            quiet=False,
            clipboard=False,
            save_file=None,
        )
        provider_cfg = config.ProviderSelection(
            tts_provider="wyoming",
            asr_provider="wyoming",
            llm_provider="ollama",
        )
        audio_out_cfg = config.AudioOutput(enable_tts=True)
        wyoming_tts_cfg = config.WyomingTTS(
            tts_wyoming_ip="mock-host",
            tts_wyoming_port=10200,
        )
        openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
        kokoro_tts_cfg = config.KokoroTTS(
            tts_kokoro_model="tts-1",
            tts_kokoro_voice="alloy",
            tts_kokoro_host="http://localhost:8000/v1",
        )

        await _async_main(
            general_cfg=general_cfg,
            text="Hello, world!",
            provider_cfg=provider_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
        )

    # Verify that the audio was "played"
    mock_wyoming_client_context.assert_called_once()
    assert mock_pyaudio_instance.streams[0].get_written_data()
