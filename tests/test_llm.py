"""Tests for the Ollama client."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents._voice_agent_common import (
    process_instruction_and_respond as process_and_update_clipboard,
)
from agent_cli.agents.autocorrect import _process_text as get_llm_response
from agent_cli.services.local.llm import build_agent

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def test_build_agent_openai_no_key():
    """Test that building the agent with OpenAI provider fails without an API key."""
    provider_cfg = config.ProviderSelection(
        llm_provider="openai",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="http://mockhost:1234")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    with pytest.raises(ValueError, match="OpenAI API key is not set."):
        build_agent(provider_cfg, ollama_cfg, openai_llm_cfg)


def test_build_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test building the agent."""
    monkeypatch.setenv("OLLAMA_HOST", "http://mockhost:1234")
    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="http://mockhost:1234")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    agent = build_agent(provider_cfg, ollama_cfg, openai_llm_cfg)

    assert agent.model.model_name == "test-model"


@pytest.mark.asyncio
@patch("agent_cli.services.local.llm.build_agent")
async def test_get_llm_response(mock_build_agent: MagicMock) -> None:
    """Test getting a response from the LLM."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="hello"))
    mock_build_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test", ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    response, _ = await get_llm_response(
        "test",
        provider_cfg,
        ollama_cfg,
        openai_llm_cfg,
    )

    assert response == "hello"
    mock_build_agent.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services.local.llm.build_agent")
async def test_get_llm_response_error(mock_build_agent: MagicMock) -> None:
    """Test getting a response from the LLM when an error occurs."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("test error"))
    mock_build_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test", ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    with pytest.raises(Exception, match="test error"):
        await get_llm_response(
            "test",
            provider_cfg,
            ollama_cfg,
            openai_llm_cfg,
        )
    mock_build_agent.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services.local.llm.build_agent")
async def test_get_llm_response_error_exit(mock_build_agent: MagicMock):
    """Test getting a response from the LLM when an error occurs and exit_on_error is True."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("test error"))
    mock_build_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test", ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    with pytest.raises(Exception, match="test error"):
        await get_llm_response(
            "test",
            provider_cfg,
            ollama_cfg,
            openai_llm_cfg,
        )


@patch("agent_cli.agents._voice_agent_common.get_llm_service")
def test_process_and_update_clipboard(
    mock_get_llm_service: MagicMock,
) -> None:
    """Test the process_and_update_clipboard function."""
    mock_llm_service = MagicMock()

    async def mock_chat_generator() -> AsyncGenerator[str, None]:
        yield "hello"

    mock_llm_service.chat.return_value = mock_chat_generator()
    mock_get_llm_service.return_value = mock_llm_service
    mock_live = MagicMock()

    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test", ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)
    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        quiet=True,
        clipboard=True,
    )
    audio_out_cfg = config.AudioOutput(enable_tts=False)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=10200,
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    asyncio.run(
        process_and_update_clipboard(
            instruction="test",
            original_text="test",
            provider_config=provider_cfg,
            general_config=general_cfg,
            ollama_config=ollama_cfg,
            openai_llm_config=openai_llm_cfg,
            audio_output_config=audio_out_cfg,
            wyoming_tts_config=wyoming_tts_cfg,
            openai_tts_config=openai_tts_cfg,
            system_prompt="test",
            agent_instructions="test",
            live=mock_live,
            logger=MagicMock(),
        ),
    )

    # Verify get_llm_response was called with the right parameters
    mock_get_llm_service.assert_called_once()
    mock_llm_service.chat.assert_called_once()
