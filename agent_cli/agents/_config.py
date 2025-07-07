"""Data classes for agent configurations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class LLMConfig:
    """LLM configuration parameters."""

    model: str
    ollama_host: str


@dataclass
class ASRConfig:
    """ASR configuration parameters."""

    server_ip: str
    server_port: int
    input_device_index: int | None
    input_device_name: str | None
    list_input_devices: bool


@dataclass
class TTSConfig:
    """TTS configuration parameters."""

    enabled: bool
    server_ip: str
    server_port: int
    voice_name: str | None
    language: str | None
    speaker: str | None
    output_device_index: int | None
    output_device_name: str | None
    list_output_devices: bool
    speed: float = 1.0  # Speech speed multiplier (1.0 = normal, 2.0 = 2x speed, etc.)


@dataclass
class GeneralConfig:
    """General configuration parameters."""

    log_level: str
    log_file: str | None
    quiet: bool
    clipboard: bool = True  # Default value since not all agents have it


@dataclass
class FileConfig:
    """File-related configuration."""

    save_file: Path | None
    last_n_messages: int = 50
    history_dir: Path | None = None

    def __post_init__(self) -> None:
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
    list_input_devices: bool
