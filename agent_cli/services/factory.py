"""Factory functions for creating service instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.services.local import (
    OllamaLLMService,
    WyomingTranscriptionService,
    WyomingTTSService,
)
from agent_cli.services.openai import (
    OpenAILLMService,
    OpenAITranscriptionService,
    OpenAITTSService,
)

if TYPE_CHECKING:
    import logging

    from agent_cli import config
    from agent_cli.services.base import ASRService, LLMService, TTSService


def get_asr_service(
    provider_config: config.ProviderSelection,
    wyoming_asr_config: config.WyomingASR,
    openai_asr_config: config.OpenAIASR,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> ASRService:
    """Get the appropriate ASR service based on the provider."""
    if provider_config.asr_provider == "openai":
        return OpenAITranscriptionService(
            openai_asr_config=openai_asr_config,
            openai_llm_config=openai_llm_config,
            logger=logger,
        )
    return WyomingTranscriptionService(
        wyoming_asr_config=wyoming_asr_config,
        logger=logger,
        quiet=quiet,
    )


def get_llm_service(
    provider_config: config.ProviderSelection,
    ollama_config: config.Ollama,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
) -> LLMService:
    """Get the appropriate LLM service based on the provider."""
    if provider_config.llm_provider == "openai":
        return OpenAILLMService(openai_llm_config=openai_llm_config, logger=logger)
    return OllamaLLMService(ollama_config=ollama_config, logger=logger)


def get_tts_service(
    provider_config: config.ProviderSelection,
    wyoming_tts_config: config.WyomingTTS,
    openai_tts_config: config.OpenAITTS,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> TTSService:
    """Get the appropriate TTS service based on the provider."""
    if provider_config.tts_provider == "openai":
        return OpenAITTSService(
            openai_tts_config=openai_tts_config,
            openai_llm_config=openai_llm_config,
            logger=logger,
        )
    return WyomingTTSService(
        wyoming_tts_config=wyoming_tts_config,
        logger=logger,
        quiet=quiet,
    )
