"""Factory functions for creating services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.services.local.llm import OllamaLLMService
from agent_cli.services.openai.llm import OpenAILLMService

if TYPE_CHECKING:
    from agent_cli import config
    from agent_cli.services.base import LLMService


def get_llm_service(
    provider_config: config.ProviderSelection,
    ollama_config: config.Ollama,
    openai_config: config.OpenAILLM,
    **kwargs,
) -> LLMService:
    """Get the LLM service based on the provider."""
    if provider_config.llm_provider == "openai":
        return OpenAILLMService(openai_config=openai_config, **kwargs)
    return OllamaLLMService(ollama_config=ollama_config, **kwargs)
