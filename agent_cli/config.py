"""Pydantic models for agent configurations, aligned with CLI option groups."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from agent_cli.core.utils import console

USER_CONFIG_PATH = Path.home() / ".config" / "agent-cli" / "config.toml"

CONFIG_PATHS = [
    Path("agent-cli-config.toml"),
    USER_CONFIG_PATH,
]


def _normalize_provider_value(field: str, value: str) -> str:
    """Map deprecated provider names to their replacements."""
    alias_map = _DEPRECATED_PROVIDER_ALIASES.get(field, {})
    normalized = value.lower()
    if normalized in alias_map:
        replacement = alias_map[normalized]
        console.print(
            f"[yellow]Deprecated provider '{value}' for {field.replace('_', '-')}."
            f" Using '{replacement}' instead.[/yellow]",
        )
        return replacement
    return value


_DEPRECATED_PROVIDER_ALIASES: dict[str, dict[str, str]] = {
    "llm_provider": {"local": "ollama"},
    "asr_provider": {"local": "wyoming"},
    "tts_provider": {"local": "wyoming"},
}

# --- Panel: Provider Selection ---


class ProviderSelection(BaseModel):
    """Configuration for selecting service providers."""

    llm_provider: Literal["ollama", "openai", "gemini"]
    asr_provider: Literal["wyoming", "openai", "gemini"]
    tts_provider: Literal["wyoming", "openai", "kokoro", "gemini"]

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalize_llm_provider(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_provider_value("llm_provider", v)
        return v

    @field_validator("asr_provider", mode="before")
    @classmethod
    def _normalize_asr_provider(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_provider_value("asr_provider", v)
        return v

    @field_validator("tts_provider", mode="before")
    @classmethod
    def _normalize_tts_provider(cls, v: str) -> str:
        if isinstance(v, str):
            return _normalize_provider_value("tts_provider", v)
        return v


# --- Panel: LLM Configuration ---


class Ollama(BaseModel):
    """Configuration for the local Ollama LLM provider."""

    llm_ollama_model: str
    llm_ollama_host: str


class OpenAILLM(BaseModel):
    """Configuration for the OpenAI LLM provider."""

    llm_openai_model: str
    openai_api_key: str | None = None
    openai_base_url: str | None = None


class GeminiLLM(BaseModel):
    """Configuration for the Gemini LLM provider."""

    llm_gemini_model: str
    gemini_api_key: str | None = None


# --- Panel: ASR (Audio) Configuration ---


class AudioInput(BaseModel):
    """Configuration for audio input devices."""

    input_device_index: int | None = None
    input_device_name: str | None = None


class WyomingASR(BaseModel):
    """Configuration for the Wyoming ASR provider."""

    asr_wyoming_ip: str
    asr_wyoming_port: int


class OpenAIASR(BaseModel):
    """Configuration for the OpenAI-compatible ASR provider."""

    asr_openai_model: str
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    asr_openai_prompt: str | None = None


class GeminiASR(BaseModel):
    """Configuration for the Gemini ASR provider."""

    asr_gemini_model: str
    gemini_api_key: str | None = None


# --- Panel: TTS (Text-to-Speech) Configuration ---


class AudioOutput(BaseModel):
    """Configuration for audio output devices and TTS behavior."""

    output_device_index: int | None = None
    output_device_name: str | None = None
    tts_speed: float = 1.0
    enable_tts: bool = False


class WyomingTTS(BaseModel):
    """Configuration for the Wyoming TTS provider."""

    tts_wyoming_ip: str
    tts_wyoming_port: int
    tts_wyoming_voice: str | None = None
    tts_wyoming_language: str | None = None
    tts_wyoming_speaker: str | None = None


class OpenAITTS(BaseModel):
    """Configuration for the OpenAI-compatible TTS provider."""

    tts_openai_model: str
    tts_openai_voice: str
    openai_api_key: str | None = None
    tts_openai_base_url: str | None = None


class KokoroTTS(BaseModel):
    """Configuration for the Kokoro TTS provider."""

    tts_kokoro_model: str
    tts_kokoro_voice: str
    tts_kokoro_host: str


class GeminiTTS(BaseModel):
    """Configuration for the Gemini TTS provider."""

    tts_gemini_model: str
    tts_gemini_voice: str
    gemini_api_key: str | None = None


# --- Panel: Wake Word Options ---


class WakeWord(BaseModel):
    """Configuration for wake word detection."""

    wake_server_ip: str
    wake_server_port: int
    wake_word: str


# --- Panel: General Options ---


class General(BaseModel):
    """General configuration parameters for logging and I/O."""

    log_level: str
    log_file: str | None = None
    quiet: bool
    clipboard: bool = True
    save_file: Path | None = None
    list_devices: bool = False

    @field_validator("save_file", mode="before")
    @classmethod
    def _expand_user_path(cls, v: str | None) -> Path | None:
        if v:
            return Path(v).expanduser()
        return None


# --- Panel: History Options ---


class History(BaseModel):
    """Configuration for conversation history."""

    history_dir: Path | None = None
    last_n_messages: int = 50

    @field_validator("history_dir", mode="before")
    @classmethod
    def _expand_user_path(cls, v: str | None) -> Path | None:
        if v:
            return Path(v).expanduser()
        return None


# --- Panel: Dev (Parallel Development) Options ---


class Dev(BaseModel):
    """Configuration for parallel development environments (git worktrees)."""

    default_agent: str | None = None
    default_editor: str | None = None
    agent_args: dict[str, list[str]] | None = (
        None  # Per-agent args, e.g. {"claude": ["--dangerously-skip-permissions"]}
    )
    setup: bool = True  # Run project setup (npm install, etc.)
    copy_env: bool = True  # Copy .env files from main repo
    fetch: bool = True  # Git fetch before creating worktree


def _config_path(config_path_str: str | None = None) -> Path | None:
    """Return a usable config path, expanding user directories."""
    if config_path_str:
        return Path(config_path_str).expanduser().resolve()

    for path in CONFIG_PATHS:
        candidate = path.expanduser()
        if candidate.exists():
            return candidate.resolve()
    return None


def load_config(config_path_str: str | None = None) -> dict[str, Any]:
    """Load the TOML configuration file and process it for nested structures.

    Supports both flat sections like [autocorrect] and nested sections like
    [memory.proxy]. Nested sections are flattened to dot-notation keys.
    """
    # Determine which config path to use
    config_path = _config_path(config_path_str)
    if config_path is None:
        return {}
    if config_path.exists():
        with config_path.open("rb") as f:
            cfg = tomllib.load(f)
            # Flatten nested sections (e.g., [memory.proxy] -> "memory.proxy")
            flattened = _flatten_nested_sections(cfg)
            return {k: _replace_dashed_keys(v) for k, v in flattened.items()}
    if config_path_str:
        console.print(
            f"[bold red]Config file not found at {config_path_str}[/bold red]",
        )
    return {}


def normalize_provider_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalize deprecated provider names in a config section."""
    normalized = dict(cfg)
    for provider_key in ("llm_provider", "asr_provider", "tts_provider"):
        if provider_key in normalized and isinstance(normalized[provider_key], str):
            normalized[provider_key] = _normalize_provider_value(
                provider_key,
                normalized[provider_key],
            )
    return normalized


def _replace_dashed_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    return {k.replace("-", "_"): v for k, v in cfg.items()}


def _flatten_nested_sections(cfg: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested TOML sections: {"a": {"b": {"x": 1}}} -> {"a.b": {"x": 1}}."""
    result = {}
    for key, value in cfg.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and any(isinstance(v, dict) for v in value.values()):
            result.update(_flatten_nested_sections(value, full_key))
        else:
            result[full_key] = value
    return result
