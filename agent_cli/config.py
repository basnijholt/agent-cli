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
    asr_wyoming_prompt: str | None = None

    def get_effective_prompt(self, extra_instructions: str | None = None) -> str | None:
        """Get the effective prompt, combining asr_wyoming_prompt with extra_instructions.

        If both are set, asr_wyoming_prompt takes precedence and extra_instructions
        is appended. If only one is set, that one is used.
        """
        if self.asr_wyoming_prompt and extra_instructions:
            return f"{self.asr_wyoming_prompt}\n\n{extra_instructions}"
        return self.asr_wyoming_prompt or extra_instructions


class OpenAIASR(BaseModel):
    """Configuration for the OpenAI-compatible ASR provider."""

    asr_openai_model: str
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    asr_openai_prompt: str | None = None

    def get_effective_prompt(self, extra_instructions: str | None = None) -> str | None:
        """Get the effective prompt, combining asr_openai_prompt with extra_instructions.

        If both are set, asr_openai_prompt takes precedence and extra_instructions
        is appended. If only one is set, that one is used.
        """
        if self.asr_openai_prompt and extra_instructions:
            return f"{self.asr_openai_prompt}\n\n{extra_instructions}"
        return self.asr_openai_prompt or extra_instructions


class GeminiASR(BaseModel):
    """Configuration for the Gemini ASR provider."""

    asr_gemini_model: str
    gemini_api_key: str | None = None
    asr_gemini_prompt: str | None = None

    def get_effective_prompt(self, extra_instructions: str | None = None) -> str | None:
        """Get the effective prompt, combining asr_gemini_prompt with extra_instructions.

        If both are set, asr_gemini_prompt takes precedence and extra_instructions
        is appended. If only one is set, that one is used.
        """
        if self.asr_gemini_prompt and extra_instructions:
            return f"{self.asr_gemini_prompt}\n\n{extra_instructions}"
        return self.asr_gemini_prompt or extra_instructions


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


# --- Common Config Bundle ---


class ProviderConfigs(BaseModel):
    """Bundle of all provider-related configs constructed from CLI parameters."""

    provider: ProviderSelection
    audio_in: AudioInput
    wyoming_asr: WyomingASR
    openai_asr: OpenAIASR
    gemini_asr: GeminiASR
    ollama: Ollama
    openai_llm: OpenAILLM
    gemini_llm: GeminiLLM
    audio_out: AudioOutput
    wyoming_tts: WyomingTTS
    openai_tts: OpenAITTS
    kokoro_tts: KokoroTTS
    gemini_tts: GeminiTTS


def create_provider_configs(
    *,
    # Provider selection
    asr_provider: str,
    llm_provider: str,
    tts_provider: str,
    # Audio input
    input_device_index: int | None,
    input_device_name: str | None,
    # Wyoming ASR
    asr_wyoming_ip: str,
    asr_wyoming_port: int,
    # OpenAI ASR
    asr_openai_model: str,
    asr_openai_base_url: str | None = None,
    asr_openai_prompt: str | None = None,
    # Gemini ASR
    asr_gemini_model: str,
    # Ollama LLM
    llm_ollama_model: str,
    llm_ollama_host: str,
    # OpenAI LLM
    llm_openai_model: str,
    # Gemini LLM
    llm_gemini_model: str,
    # Shared API keys
    openai_api_key: str | None,
    openai_base_url: str | None,
    gemini_api_key: str | None,
    # Audio output
    enable_tts: bool,
    output_device_index: int | None,
    output_device_name: str | None,
    tts_speed: float,
    # Wyoming TTS
    tts_wyoming_ip: str,
    tts_wyoming_port: int,
    tts_wyoming_voice: str | None,
    tts_wyoming_language: str | None,
    tts_wyoming_speaker: str | None,
    # OpenAI TTS
    tts_openai_model: str,
    tts_openai_voice: str,
    tts_openai_base_url: str | None,
    # Kokoro TTS
    tts_kokoro_model: str,
    tts_kokoro_voice: str,
    tts_kokoro_host: str,
    # Gemini TTS
    tts_gemini_model: str,
    tts_gemini_voice: str,
) -> ProviderConfigs:
    """Create all provider-related config objects from CLI parameters.

    This factory function centralizes the construction of provider configs
    to eliminate duplication across CLI commands.
    """
    return ProviderConfigs(
        provider=ProviderSelection(
            asr_provider=asr_provider,
            llm_provider=llm_provider,
            tts_provider=tts_provider,
        ),
        audio_in=AudioInput(
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        ),
        wyoming_asr=WyomingASR(
            asr_wyoming_ip=asr_wyoming_ip,
            asr_wyoming_port=asr_wyoming_port,
        ),
        openai_asr=OpenAIASR(
            asr_openai_model=asr_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=asr_openai_base_url or openai_base_url,
            asr_openai_prompt=asr_openai_prompt,
        ),
        gemini_asr=GeminiASR(
            asr_gemini_model=asr_gemini_model,
            gemini_api_key=gemini_api_key,
        ),
        ollama=Ollama(
            llm_ollama_model=llm_ollama_model,
            llm_ollama_host=llm_ollama_host,
        ),
        openai_llm=OpenAILLM(
            llm_openai_model=llm_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
        ),
        gemini_llm=GeminiLLM(
            llm_gemini_model=llm_gemini_model,
            gemini_api_key=gemini_api_key,
        ),
        audio_out=AudioOutput(
            enable_tts=enable_tts,
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            tts_speed=tts_speed,
        ),
        wyoming_tts=WyomingTTS(
            tts_wyoming_ip=tts_wyoming_ip,
            tts_wyoming_port=tts_wyoming_port,
            tts_wyoming_voice=tts_wyoming_voice,
            tts_wyoming_language=tts_wyoming_language,
            tts_wyoming_speaker=tts_wyoming_speaker,
        ),
        openai_tts=OpenAITTS(
            tts_openai_model=tts_openai_model,
            tts_openai_voice=tts_openai_voice,
            openai_api_key=openai_api_key,
            tts_openai_base_url=tts_openai_base_url,
        ),
        kokoro_tts=KokoroTTS(
            tts_kokoro_model=tts_kokoro_model,
            tts_kokoro_voice=tts_kokoro_voice,
            tts_kokoro_host=tts_kokoro_host,
        ),
        gemini_tts=GeminiTTS(
            tts_gemini_model=tts_gemini_model,
            tts_gemini_voice=tts_gemini_voice,
            gemini_api_key=gemini_api_key,
        ),
    )


# Parameter names used by create_provider_configs (all keyword-only)
_PROVIDER_CONFIG_PARAMS = frozenset(
    create_provider_configs.__code__.co_varnames[
        : create_provider_configs.__code__.co_kwonlyargcount
    ],
)


def create_provider_configs_from_locals(local_vars: dict[str, Any]) -> ProviderConfigs:
    """Create provider configs by extracting parameters from a locals() dict.

    This helper enables one-line config creation in CLI commands by automatically
    extracting the relevant parameters from the command's local variables.

    Usage:
        cfgs = config.create_provider_configs_from_locals(locals())
    """
    kwargs = {k: v for k, v in local_vars.items() if k in _PROVIDER_CONFIG_PARAMS}
    return create_provider_configs(**kwargs)
