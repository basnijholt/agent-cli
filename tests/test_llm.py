"""Tests for the Ollama client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services.llm import build_agent, get_llm_response, process_and_update_clipboard


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
@patch("agent_cli.services.llm.build_agent")
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

    response = await get_llm_response(
        system_prompt="test",
        agent_instructions="test",
        user_input="test",
        provider_config=provider_cfg,
        ollama_config=ollama_cfg,
        openai_config=openai_llm_cfg,
        logger=MagicMock(),
        live=MagicMock(),
    )

    assert response == "hello"
    mock_build_agent.assert_called_once()
    mock_agent.run.assert_called_once_with("test")


@pytest.mark.asyncio
@patch("agent_cli.services.llm.build_agent")
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

    response = await get_llm_response(
        system_prompt="test",
        agent_instructions="test",
        user_input="test",
        provider_config=provider_cfg,
        ollama_config=ollama_cfg,
        openai_config=openai_llm_cfg,
        logger=MagicMock(),
        live=MagicMock(),
    )

    assert response is None
    mock_build_agent.assert_called_once()
    mock_agent.run.assert_called_once_with("test")


@pytest.mark.asyncio
@patch("agent_cli.services.llm.build_agent")
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

    with pytest.raises(SystemExit):
        await get_llm_response(
            system_prompt="test",
            agent_instructions="test",
            user_input="test",
            provider_config=provider_cfg,
            ollama_config=ollama_cfg,
            openai_config=openai_llm_cfg,
            logger=MagicMock(),
            live=MagicMock(),
            exit_on_error=True,
        )


@patch("agent_cli.services.llm.get_llm_response", new_callable=AsyncMock)
def test_process_and_update_clipboard(
    mock_get_llm_response: AsyncMock,
) -> None:
    """Test the process_and_update_clipboard function."""
    mock_get_llm_response.return_value = "hello"
    mock_live = MagicMock()

    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test", ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini", openai_api_key=None)

    asyncio.run(
        process_and_update_clipboard(
            system_prompt="test",
            agent_instructions="test",
            provider_config=provider_cfg,
            ollama_config=ollama_cfg,
            openai_config=openai_llm_cfg,
            logger=MagicMock(),
            original_text="test",
            instruction="test",
            clipboard=True,
            quiet=True,
            live=mock_live,
        ),
    )

    # Verify get_llm_response was called with the right parameters
    mock_get_llm_response.assert_called_once()
    call_args = mock_get_llm_response.call_args
    assert call_args.kwargs["clipboard"] is True
    assert call_args.kwargs["quiet"] is True
    assert call_args.kwargs["live"] is mock_live
    assert call_args.kwargs["show_output"] is True
    assert call_args.kwargs["exit_on_error"] is True
