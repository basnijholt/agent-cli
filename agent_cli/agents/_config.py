"""Pydantic models for agent configurations."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


# --- LLM ---
class OllamaLLMConfig(BaseModel):
    """Configuration for the local Ollama LLM provider."""

    model: str
    host: str


class OpenAILLMConfig(BaseModel):
    """Configuration for the OpenAI LLM provider."""

    model: str
    api_key: str | None = None


class LLMConfig(BaseModel):
    """LLM configuration parameters."""

    provider: Literal["local", "openai"]
    local: OllamaLLMConfig | None = None
    openai: OpenAILLMConfig | None = None

    @property
    def config(self) -> OllamaLLMConfig | OpenAILLMConfig:
        """Return the active LLM configuration based on the provider."""
        if self.provider == "local":
            if self.local is None:
                msg = "Local LLM provider selected but no config found."
                raise ValueError(msg)
            return self.local
        if self.provider == "openai":
            if self.openai is None:
                msg = "OpenAI LLM provider selected but no config found."
                raise ValueError(msg)
            return self.openai
        msg = f"Unsupported LLM provider: {self.provider}"
        raise ValueError(msg)


# --- ASR ---
class WyomingASRConfig(BaseModel):
    """Configuration for the Wyoming ASR provider."""

    server_ip: str
    server_port: int


class OpenAIASRConfig(BaseModel):
    """Configuration for the OpenAI ASR provider."""

    model: str = "whisper-1"
    api_key: str | None = None


class ASRConfig(BaseModel):
    """ASR configuration parameters."""

    provider: Literal["local", "openai"]
    input_device_index: int | None = None
    input_device_name: str | None = None
    local: WyomingASRConfig | None = None
    openai: OpenAIASRConfig | None = None

    @property
    def config(self) -> WyomingASRConfig | OpenAIASRConfig:
        """Return the active ASR configuration based on the provider."""
        if self.provider == "local":
            if self.local is None:
                msg = "Local ASR provider selected but no config found."
                raise ValueError(msg)
            return self.local
        if self.provider == "openai":
            if self.openai is None:
                msg = "OpenAI ASR provider selected but no config found."
                raise ValueError(msg)
            return self.openai
        msg = f"Unsupported ASR provider: {self.provider}"
        raise ValueError(msg)


# --- TTS ---
class WyomingTTSConfig(BaseModel):
    """Configuration for the Wyoming TTS provider."""

    server_ip: str
    server_port: int
    voice_name: str | None = None
    language: str | None = None
    speaker: str | None = None


class OpenAITTSConfig(BaseModel):
    """Configuration for the OpenAI TTS provider."""

    model: str = "tts-1"
    voice: str = "alloy"
    api_key: str | None = None


class TTSConfig(BaseModel):
    """TTS configuration parameters."""

    enabled: bool
    provider: Literal["local", "openai"]
    output_device_index: int | None = None
    output_device_name: str | None = None
    speed: float = 1.0
    local: WyomingTTSConfig | None = None
    openai: OpenAITTSConfig | None = None

    @property
    def config(self) -> WyomingTTSConfig | OpenAITTSConfig:
        """Return the active TTS configuration based on the provider."""
        if self.provider == "local":
            if self.local is None:
                msg = "Local TTS provider selected but no config found."
                raise ValueError(msg)
            return self.local
        if self.provider == "openai":
            if self.openai is None:
                msg = "OpenAI TTS provider selected but no config found."
                raise ValueError(msg)
            return self.openai
        msg = f"Unsupported TTS provider: {self.provider}"
        raise ValueError(msg)


# --- General & File Configs (remain mostly unchanged) ---
class GeneralConfig(BaseModel):
    """General configuration parameters."""

    log_level: str
    log_file: str | None = None
    quiet: bool
    list_devices: bool
    clipboard: bool = True


class FileConfig(BaseModel):
    """File-related configuration."""

    save_file: Path | None = None
    last_n_messages: int = 50
    history_dir: Path | None = None

    @field_validator("history_dir", "save_file", mode="before")
    @classmethod
    def _expand_user_path(cls, v: str | None) -> Path | None:
        if v:
            return Path(v).expanduser()
        return None


class WakeWordConfig(BaseModel):
    """Wake Word configuration options."""

    server_ip: str
    server_port: int
    wake_word_name: str
    input_device_index: int | None = None
    input_device_name: str | None = None
