"""End-to-end tests for the voice assistant agent with simplified mocks."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
)
from agent_cli.agents.voice_assistant import async_main
from tests.mocks.audio import MockPyAudio
from tests.mocks.llm import MockLLMAgent
from tests.mocks.wyoming import MockASRClient, MockTTSClient

if TYPE_CHECKING:
    from types import TracebackType

    from rich.console import Console


class MockSignalContext:
    """A mock signal context for testing."""

    def __init__(self) -> None:
        """Initialize the mock signal context."""
        self.ctrl_c_pressed = False

    async def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    async def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager."""


def setup_mocks(
    mock_build_agent: MagicMock,
    mock_tts_wyoming_client_context: MagicMock,
    mock_asr_wyoming_client_context: MagicMock,
    llm_responses: dict[str, str],
    mock_pyaudio_device_info: list[dict],
) -> tuple[MockLLMAgent, MockPyAudio]:
    """Set up all the necessary mocks for the e2e test."""
    mock_llm_agent = MockLLMAgent(llm_responses)
    mock_build_agent.return_value = mock_llm_agent
    mock_asr_client = MockASRClient("this is a test")
    mock_tts_client = MockTTSClient(b"fake audio data")
    mock_asr_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client
    mock_tts_wyoming_client_context.return_value.__aenter__.return_value = mock_tts_client
    return mock_llm_agent, MockPyAudio(mock_pyaudio_device_info)


def get_configs(
    mock_console: Console,
) -> tuple[GeneralConfig, ASRConfig, LLMConfig, TTSConfig, FileConfig]:
    """Get all the necessary configs for the e2e test."""
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=False, clipboard=True)
    general_cfg.__dict__["console"] = mock_console
    asr_config = ASRConfig(
        server_ip="mock-asr-host",
        server_port=10300,
        input_device_index=0,
        input_device_name=None,
        list_input_devices=False,
    )
    llm_config = LLMConfig(model="test-model", ollama_host="http://localhost:11434")
    tts_config = TTSConfig(
        enabled=True,
        server_ip="mock-tts-host",
        server_port=10200,
        voice_name=None,
        language=None,
        speaker=None,
        output_device_index=None,
        output_device_name=None,
        list_output_devices=False,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None)
    return general_cfg, asr_config, llm_config, tts_config, file_config


@pytest.mark.asyncio
@patch("agent_cli.llm.build_agent")
@patch("agent_cli.tts.wyoming_client_context")
@patch("agent_cli.asr.wyoming_client_context")
@patch("agent_cli.agents.voice_assistant.pyaudio_context")
@patch("agent_cli.tts.pyaudio_context")
@patch("agent_cli.agents.voice_assistant.signal_handling_context")
@patch("agent_cli.agents.voice_assistant.get_clipboard_text", return_value="test clipboard text")
@patch("agent_cli.llm.pyperclip.copy")
@patch("agent_cli.agents.voice_assistant.pyperclip.paste", return_value="mocked paste")
async def test_voice_assistant_e2e(
    mock_paste: MagicMock,  # noqa: ARG001
    mock_copy: MagicMock,
    mock_get_clipboard: MagicMock,  # noqa: ARG001
    mock_signal_context: MagicMock,
    mock_tts_pyaudio: MagicMock,
    mock_va_pyaudio: MagicMock,
    mock_asr_wyoming: MagicMock,
    mock_tts_wyoming: MagicMock,
    mock_build_agent: MagicMock,
    llm_responses: dict[str, str],
    mock_pyaudio_device_info: list[dict],
    mock_console: Console,
) -> None:
    """Test end-to-end voice assistant functionality with simplified mocks."""
    mock_signal_context.return_value = MockSignalContext()
    mock_llm_agent, mock_pyaudio_instance = setup_mocks(
        mock_build_agent,
        mock_tts_wyoming,
        mock_asr_wyoming,
        llm_responses,
        mock_pyaudio_device_info,
    )
    general_cfg, asr_config, llm_config, tts_config, file_config = get_configs(mock_console)
    mock_va_pyaudio.return_value.__enter__.return_value = mock_pyaudio_instance
    mock_tts_pyaudio.return_value.__enter__.return_value = mock_pyaudio_instance

    stop_event = asyncio.Event()
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

    await async_main(
        general_cfg=general_cfg,
        asr_config=asr_config,
        llm_config=llm_config,
        tts_config=tts_config,
        file_config=file_config,
    )

    # Assertions
    mock_build_agent.assert_called_once()
    assert mock_llm_agent.call_history
    assert mock_pyaudio_instance.streams[1].get_written_data()
    mock_copy.assert_called_once()
