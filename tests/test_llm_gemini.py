"""Tests for the Gemini LLM provider."""

from __future__ import annotations

import pytest

from agent_cli import config
from agent_cli.services.llm import build_agent


@pytest.mark.asyncio
async def test_build_agent_with_gemini() -> None:
    """Test that the build_agent function can build an agent with the Gemini provider."""
    provider_config = config.ProviderSelection(
        llm_provider="gemini",
        asr_provider="local",
        tts_provider="local",
    )
    gemini_config = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    ollama_config = config.Ollama(
        llm_ollama_model="qwen3:4b",
        llm_ollama_host="http://localhost:11434",
    )
    openai_config = config.OpenAILLM(
        llm_openai_model="gpt-4o-mini",
        openai_api_key="test-key",
    )

    agent = build_agent(
        provider_config=provider_config,
        ollama_config=ollama_config,
        openai_config=openai_config,
        gemini_config=gemini_config,
    )
    assert agent is not None
