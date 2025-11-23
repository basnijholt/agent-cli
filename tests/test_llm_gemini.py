"""Tests for the Gemini LLM provider."""

from __future__ import annotations

import pytest

from agent_cli import config
from agent_cli.constants import DEFAULT_OPENAI_MODEL
from agent_cli.services.llm import create_llm_agent


@pytest.mark.asyncio
async def test_create_llm_agent_with_gemini() -> None:
    """Test that the create_llm_agent function can build an agent with the Gemini provider."""
    provider_cfg = config.ProviderSelection(
        llm_provider="gemini",
        asr_provider="wyoming",
        tts_provider="wyoming",
    )
    gemini_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="gemma3:4b",
        llm_ollama_host="http://localhost:11434",
    )
    openai_cfg = config.OpenAILLM(
        llm_openai_model=DEFAULT_OPENAI_MODEL,
        openai_api_key="test-key",
    )

    agent = create_llm_agent(
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_cfg,
        gemini_cfg=gemini_cfg,
    )
    assert agent is not None
