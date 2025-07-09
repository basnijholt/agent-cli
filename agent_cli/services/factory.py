"""Factory functions for creating services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.services.local.asr import WyomingASRService
from agent_cli.services.local.llm import OllamaLLMService
from agent_cli.services.openai.asr import OpenAIASRService
from agent_cli.services.openai.llm import OpenAILLMService

if TYPE_CHECKING:
    from agent_cli import config
    from agent_cli.services.base import ASRService, LLMService


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


def get_asr_service(
    provider_config: config.ProviderSelection,
    wyoming_asr_config: config.WyomingASR,
    openai_asr_config: config.OpenAIASR,
    **kwargs,
) -> ASRService:
    """Get the ASR service based on the provider."""
    if provider_config.asr_provider == "openai":
        return OpenAIASRService(openai_asr_config=openai_asr_config, **kwargs)
    return WyomingASRService(wyoming_asr_config=wyoming_asr_config, **kwargs)
