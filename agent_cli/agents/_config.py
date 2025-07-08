"""Data classes for agent configurations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pathlib import Path


# --- LLM ---
@dataclass
class OllamaLLMConfig:
    """Configuration for the local Ollama LLM provider."""

    model: str
    host: str


@dataclass
class OpenAILLMConfig:
    """Configuration for the OpenAI LLM provider."""

    model: str
    api_key: str | None = None


@dataclass
class LLMConfig:
    """LLM configuration parameters."""

    provider: Literal["local", "openai"]
    providers: dict[str, Any] = field(default_factory=dict)


# --- ASR ---
@dataclass
class WyomingASRConfig:
    """Configuration for the Wyoming ASR provider."""

    server_ip: str
    server_port: int


@dataclass
class OpenAIASRConfig:
    """Configuration for the OpenAI ASR provider."""

    model: str = "whisper-1"
    api_key: str | None = None


@dataclass
class ASRConfig:
    """ASR configuration parameters."""

    provider: Literal["local", "openai"]
    input_device_index: int | None
    input_device_name: str | None
    providers: dict[str, Any] = field(default_factory=dict)


# --- TTS ---
@dataclass
class WyomingTTSConfig:
    """Configuration for the Wyoming TTS provider."""

    server_ip: str
    server_port: int
    voice_name: str | None
    language: str | None
    speaker: str | None


@dataclass
class OpenAITTSConfig:
    """Configuration for the OpenAI TTS provider."""

    model: str = "tts-1"
    voice: str = "alloy"
    api_key: str | None = None


@dataclass
class TTSConfig:
    """TTS configuration parameters."""

    enabled: bool
    provider: Literal["local", "openai"]
    output_device_index: int | None
    output_device_name: str | None
    speed: float = 1.0
    providers: dict[str, Any] = field(default_factory=dict)


# --- General & File Configs (remain mostly unchanged) ---
@dataclass
class GeneralConfig:
    """General configuration parameters."""

    log_level: str
    log_file: str | None
    quiet: bool
    list_devices: bool
    clipboard: bool = True


@dataclass
class FileConfig:
    """File-related configuration."""

    save_file: Path | None
    last_n_messages: int = 50
    history_dir: Path | None = None

    def __post_init__(self) -> None:
        """Expand user paths for history and save file."""
        if self.history_dir:
            self.history_dir = self.history_dir.expanduser()
        if self.save_file:
            self.save_file = self.save_file.expanduser()


@dataclass
class WakeWordConfig:
    """Wake Word configuration options."""

    server_ip: str
    server_port: int
    wake_word_name: str
    input_device_index: int | None
    input_device_name: str | None
