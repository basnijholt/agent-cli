"""Shared configuration utilities for agent-cli."""

from __future__ import annotations

from typing import Any

from agent_cli import config


def create_provider_config_from_defaults(defaults: dict[str, Any]) -> config.ProviderSelection:
    """Create ProviderSelection from configuration defaults."""
    return config.ProviderSelection(
        asr_provider=defaults.get("asr_provider", "local"),
        llm_provider=defaults.get("llm_provider", "local"),
        tts_provider=defaults.get("tts_provider", "local"),
    )


def create_llm_configs(
    provider_cfg: config.ProviderSelection,
    defaults: dict[str, Any],
) -> tuple[config.Ollama, config.OpenAILLM, config.GeminiLLM]:
    """Create LLM configurations based on the selected provider.

    Returns all three configs, with appropriate defaults for the selected provider.
    """
    # Ollama config
    if provider_cfg.llm_provider == "local":
        ollama_cfg = config.Ollama(
            llm_ollama_model=defaults.get("llm_ollama_model", "qwen3:4b"),
            llm_ollama_host=defaults.get("llm_ollama_host", "http://localhost:11434"),
        )
    else:
        # Default Ollama config when not selected
        ollama_cfg = config.Ollama(
            llm_ollama_model="llama2",
            llm_ollama_host="http://localhost:11434",
        )

    # OpenAI config
    if provider_cfg.llm_provider == "openai":
        openai_cfg = config.OpenAILLM(
            llm_openai_model=defaults.get("llm_openai_model", "gpt-4o-mini"),
            openai_api_key=defaults.get("openai_api_key"),
        )
    else:
        # Default OpenAI config when not selected
        openai_cfg = config.OpenAILLM(
            llm_openai_model="gpt-4o-mini",
            openai_api_key=None,
        )

    # Gemini config
    if provider_cfg.llm_provider == "gemini":
        gemini_cfg = config.GeminiLLM(
            llm_gemini_model=defaults.get("llm_gemini_model", "gemini-2.5-flash"),
            gemini_api_key=defaults.get("gemini_api_key"),
        )
    else:
        # Default Gemini config when not selected
        gemini_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-pro",
            gemini_api_key=None,
        )

    return ollama_cfg, openai_cfg, gemini_cfg


def create_asr_configs(
    provider_cfg: config.ProviderSelection,  # noqa: ARG001
    defaults: dict[str, Any],
) -> tuple[config.WyomingASR, config.OpenAIASR]:
    """Create ASR configurations based on the selected provider."""
    wyoming_cfg = config.WyomingASR(
        asr_wyoming_ip=defaults.get("asr_wyoming_ip", "localhost"),
        asr_wyoming_port=defaults.get("asr_wyoming_port", 10300),
    )

    openai_cfg = config.OpenAIASR(
        asr_openai_model=defaults.get("asr_openai_model", "whisper-1"),
        openai_api_key=defaults.get("openai_api_key"),
    )

    return wyoming_cfg, openai_cfg


def merge_extra_instructions(*instructions: str | None) -> str:
    """Merge multiple instruction strings, filtering out None values."""
    parts = [inst for inst in instructions if inst]
    return "\n\n".join(parts)
