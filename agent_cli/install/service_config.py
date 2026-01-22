"""Shared service configuration for cross-platform service management."""

# pylint: disable=duplicate-code

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServiceConfig:
    """Configuration for a service.

    Platform-agnostic service definition used by both launchd (macOS)
    and systemd (Linux) implementations.
    """

    name: str
    display_name: str
    description: str
    extra: str  # uv extra to install (e.g., "whisper", "tts-kokoro"), empty for external
    command_args: list[str]  # Additional args after "agent-cli server <name>"
    external: bool = False  # True for external services (ollama) that aren't agent-cli servers
    python_version: str | None = None  # Pin Python version for dependencies without py3.14 wheels


# Available services for installation
SERVICES: dict[str, ServiceConfig] = {
    "whisper": ServiceConfig(
        name="whisper",
        display_name="Whisper ASR",
        description="Speech-to-text server (ports 10300/10301)",
        extra="whisper",
        command_args=[],
        python_version="3.13",  # onnxruntime lacks py3.14 wheels
    ),
    "tts": ServiceConfig(
        name="tts",
        display_name="Kokoro TTS",
        description="Text-to-speech server (ports 10200/10201)",
        extra="tts-kokoro",
        command_args=["--backend", "kokoro"],
        python_version="3.13",  # onnxruntime lacks py3.14 wheels
    ),
    "transcription-proxy": ServiceConfig(
        name="transcription-proxy",
        display_name="Transcription Proxy",
        description="Proxy server for ASR providers (port 61337)",
        extra="server",
        command_args=[],
    ),
    "ollama": ServiceConfig(
        name="ollama",
        display_name="Ollama",
        description="Local LLM inference server (port 11434)",
        extra="",
        command_args=[],
        external=True,
    ),
}


def find_uv(extra_paths: list[Path] | None = None) -> Path | None:
    """Find uv executable, preferring system paths over virtualenv."""
    paths = [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
    ]
    if extra_paths:
        paths = extra_paths + paths

    for path in paths:
        if path.is_file() and os.access(path, os.X_OK):
            return path

    # Fallback to which
    which_result = shutil.which("uv")
    return Path(which_result) if which_result else None


def check_uv_installed(extra_paths: list[Path] | None = None) -> tuple[bool, Path | None]:
    """Check if uv is installed."""
    uv_path = find_uv(extra_paths)
    return (uv_path is not None, uv_path)


def install_uv() -> tuple[bool, str]:
    """Install uv using the official installer."""
    try:
        result = subprocess.run(
            ["curl", "-LsSf", "https://astral.sh/uv/install.sh"],  # noqa: S607
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["sh"],  # noqa: S607
            input=result.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        return True, "uv installed successfully"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to install uv: {e}"
