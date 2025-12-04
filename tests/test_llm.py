"""Tests for the Ollama client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.constants import DEFAULT_OPENAI_MODEL
from agent_cli.services.llm import create_llm_agent, get_llm_response, process_and_update_clipboard


def test_create_llm_agent_openai_no_key():
    """Test that building the agent with OpenAI provider fails without an API key."""
    provider_cfg = config.ProviderSelection(
        llm_provider="openai",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="test-model",
        llm_ollama_host="http://mockhost:1234",
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    with pytest.raises(ValueError, match="OpenAI API key is not set"):
        create_llm_agent(provider_cfg, ollama_cfg, openai_llm_cfg, gemini_llm_cfg)


def test_create_llm_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test building the agent."""
    monkeypatch.setenv("LLM_OLLAMA_HOST", "http://mockhost:1234")
    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="test-model",
        llm_ollama_host="http://mockhost:1234",
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    agent = create_llm_agent(provider_cfg, ollama_cfg, openai_llm_cfg, gemini_llm_cfg)

    assert agent.model.model_name == "test-model"


@pytest.mark.asyncio
@patch("agent_cli.services.llm.create_llm_agent")
async def test_get_llm_response(mock_create_llm_agent: MagicMock) -> None:
    """Test getting a response from the LLM."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(output="hello"))
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    response = await get_llm_response(
        system_prompt="test",
        agent_instructions="test",
        user_input="test",
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        logger=MagicMock(),
        live=MagicMock(),
    )

    assert response == "hello"
    mock_create_llm_agent.assert_called_once()
    mock_agent.run.assert_called_once_with("test")


@pytest.mark.asyncio
@patch("agent_cli.services.llm.create_llm_agent")
async def test_get_llm_response_error(mock_create_llm_agent: MagicMock) -> None:
    """Test getting a response from the LLM when an error occurs."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("test error"))
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    response = await get_llm_response(
        system_prompt="test",
        agent_instructions="test",
        user_input="test",
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        logger=MagicMock(),
        live=MagicMock(),
    )

    assert response is None
    mock_create_llm_agent.assert_called_once()
    mock_agent.run.assert_called_once_with("test")


@pytest.mark.asyncio
@patch("agent_cli.services.llm.create_llm_agent")
async def test_get_llm_response_error_exit(mock_create_llm_agent: MagicMock):
    """Test getting a response from the LLM when an error occurs and exit_on_error is True."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("test error"))
    mock_create_llm_agent.return_value = mock_agent

    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    with pytest.raises(SystemExit):
        await get_llm_response(
            system_prompt="test",
            agent_instructions="test",
            user_input="test",
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_cfg=openai_llm_cfg,
            gemini_cfg=gemini_llm_cfg,
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
        llm_provider="ollama",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="test")
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key=None,
        openai_base_url=None,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    asyncio.run(
        process_and_update_clipboard(
            system_prompt="test",
            agent_instructions="test",
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_cfg=openai_llm_cfg,
            gemini_cfg=gemini_llm_cfg,
            logger=MagicMock(),
            original_text="test",
            instruction="test",
            clipboard=True,
            quiet=True,
            live=mock_live,
            context="Recent context",
        ),
    )

    # Verify get_llm_response was called with the right parameters
    mock_get_llm_response.assert_called_once()
    call_args = mock_get_llm_response.call_args
    assert call_args.kwargs["clipboard"] is True
    assert call_args.kwargs["quiet"] is True
    assert call_args.kwargs["live"] is mock_live
    assert call_args.kwargs["show_output"] is True
    assert call_args.kwargs["exit_on_error"] is False
    assert "<context>" in call_args.kwargs["user_input"]
    assert "Recent context" in call_args.kwargs["user_input"]
