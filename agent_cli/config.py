"""Pydantic models for agent configurations, aligned with CLI option groups."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from agent_cli.core.utils import console

CONFIG_PATHS = [
    Path("agent-cli-config.toml"),
    Path.home() / ".config" / "agent-cli" / "config.toml",
]

# --- Panel: Provider Selection ---


class ProviderSelection(BaseModel):
    """Configuration for selecting service providers."""

    llm_provider: Literal["local", "openai", "gemini"]
    asr_provider: Literal["local", "openai"]
    tts_provider: Literal["local", "openai", "kokoro"]


# --- Panel: LLM Configuration ---


class Ollama(BaseModel):
    """Configuration for the local Ollama LLM provider."""

    llm_ollama_model: str
    llm_ollama_host: str


class OpenAILLM(BaseModel):
    """Configuration for the OpenAI LLM provider."""

    llm_openai_model: str
    openai_api_key: str | None = None


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
    """Configuration for the OpenAI ASR provider."""

    asr_openai_model: str
    openai_api_key: str | None = None


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
    """Configuration for the OpenAI TTS provider."""

    tts_openai_model: str
    tts_openai_voice: str
    openai_api_key: str | None = None


class KokoroTTS(BaseModel):
    """Configuration for the Kokoro TTS provider."""

    tts_kokoro_model: str
    tts_kokoro_voice: str
    tts_kokoro_host: str


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


def _config_path(config_path_str: str | None = None) -> Path | None:
    if config_path_str:
        return Path(config_path_str)
    return next((p for p in CONFIG_PATHS if p.exists()), None)


def load_config(config_path_str: str | None = None) -> dict[str, Any]:
    """Load the TOML configuration file and process it for nested structures."""
    # Determine which config path to use
    config_path = _config_path(config_path_str)
    if config_path is None:
        return {}
    if config_path.exists():
        with config_path.open("rb") as f:
            cfg = tomllib.load(f)
            return {k: _replace_dashed_keys(v) for k, v in cfg.items()}
    if config_path_str:
        console.print(
            f"[bold red]Config file not found at {config_path_str}[/bold red]",
        )
    return {}


def _replace_dashed_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    return {k.replace("-", "_"): v for k, v in cfg.items()}
