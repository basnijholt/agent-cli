"""Shared service configuration for cross-platform service management."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class ServiceConfig:
    """Configuration for a service.

    Platform-agnostic service definition used by both launchd (macOS)
    and systemd (Linux) implementations.
    """

    name: str
    display_name: str
    description: str
    extra: str  # uv extras to install (e.g., "server,kokoro,wyoming"), empty for external
    command_args: list[str]  # Additional args after the base command
    python_version: str | None = (
        None  # Pin Python version for dependencies without newer Python wheels
    )
    macos_extra: str | None = None  # Override extra on macOS (e.g., whisper-mlx)
    # Custom command path (default: ["server", name]). For non-server commands like "memory proxy"
    command: list[str] | None = None


# TTS services that are mutually exclusive (same ports)
TTS_SERVICES = ("tts-kokoro", "tts-piper")


def detect_preferred_tts() -> str:
    """Detect the preferred TTS backend based on platform.

    Returns tts-kokoro on macOS (MPS) or Linux with CUDA hints,
    otherwise tts-piper for CPU-only systems.
    """
    system = platform.system()
    if system == "Darwin":
        # macOS has MPS on Apple Silicon
        return "tts-kokoro"
    if system == "Linux":
        # Check for CUDA availability hints
        cuda_hints = [
            Path("/usr/local/cuda").exists(),
            shutil.which("nvidia-smi") is not None,
            os.environ.get("CUDA_HOME") is not None,
        ]
        if any(cuda_hints):
            return "tts-kokoro"
    return "tts-piper"


def get_default_services() -> list[str]:
    """Get default services for --all, picking one TTS backend automatically."""
    preferred_tts = detect_preferred_tts()
    excluded_tts = "tts-piper" if preferred_tts == "tts-kokoro" else "tts-kokoro"
    return [name for name in SERVICES if name != excluded_tts]


# Available services for installation
SERVICES: dict[str, ServiceConfig] = {
    "whisper": ServiceConfig(
        name="whisper",
        display_name="Whisper ASR",
        description="Speech-to-text server (ports 10300/10301)",
        extra="server,faster-whisper,wyoming",
        command_args=[],
        python_version=None,
        macos_extra="server,mlx-whisper,wyoming",
    ),
    "tts-kokoro": ServiceConfig(
        name="tts",  # Server command is still "tts"
        display_name="Kokoro TTS",
        description="Text-to-speech with Kokoro (GPU, ports 10200/10201)",
        extra="server,kokoro,wyoming",
        command_args=["--backend", "kokoro"],
        python_version="3.12",  # curated-tokenizers (via kokoro→misaki→spacy) lacks py3.13 wheels
    ),
    "tts-piper": ServiceConfig(
        name="tts",  # Server command is still "tts"
        display_name="Piper TTS",
        description="Text-to-speech with Piper (CPU, ports 10200/10201)",
        extra="server,piper,wyoming",
        command_args=["--backend", "piper"],
    ),
    "transcription-proxy": ServiceConfig(
        name="transcription-proxy",
        display_name="Transcription Proxy",
        description="Proxy server for ASR providers (port 61337)",
        extra="server",
        command_args=[],
    ),
    "memory": ServiceConfig(
        name="memory",
        display_name="Memory Proxy",
        description="Long-term memory proxy for LLMs (port 8100)",
        extra="memory",
        command_args=[],
        command=["memory", "proxy"],
    ),
    "rag": ServiceConfig(
        name="rag",
        display_name="RAG Proxy",
        description="Document retrieval proxy for LLMs (port 8000)",
        extra="rag",
        command_args=[],
        command=["rag-proxy"],
    ),
}


def build_service_command(
    service: ServiceConfig,
    uv_path: Path,
    *,
    use_macos_extra: bool = False,
) -> list[str]:
    """Build the command args for running a service via uv tool run."""
    extra = (service.macos_extra or service.extra) if use_macos_extra else service.extra

    args = [str(uv_path), "tool", "run"]

    # Add python version constraint (skip on macOS when using macos_extra,
    # since macos_extra typically avoids deps that need version pinning)
    if service.python_version and not (use_macos_extra and service.macos_extra):
        args.extend(["--python", service.python_version])

    # Build the command: either custom command path or default "server <name>"
    cmd_path = service.command or ["server", service.name]

    args.extend(
        [
            "--from",
            f"agent-cli[{extra}]",
            "agent-cli",
            *cmd_path,
            *service.command_args,
        ],
    )
    return args


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


# Shared result dataclasses used by both launchd and systemd modules


@dataclass
class ServiceStatus:
    """Status of a service."""

    name: str
    installed: bool
    running: bool
    pid: int | None = None


@dataclass
class InstallResult:
    """Result of installing a service."""

    success: bool
    message: str
    log_dir: Path | None = None


@dataclass
class UninstallResult:
    """Result of uninstalling a service."""

    success: bool
    message: str
    was_running: bool = False


class ServiceManager(NamedTuple):
    """Platform-specific service manager interface.

    Both launchd (macOS) and systemd (Linux) modules provide these functions.
    """

    check_uv_installed: Callable[[], tuple[bool, Path | None]]
    install_uv: Callable[[], tuple[bool, str]]
    install_service: Callable[[str], InstallResult]
    uninstall_service: Callable[[str], UninstallResult]
    get_service_status: Callable[[str], ServiceStatus]
    get_log_command: Callable[[str], str]
    get_recent_logs: Callable[[str, int], list[str]]


def get_service_manager() -> ServiceManager:
    """Get the platform-specific service manager.

    Returns a ServiceManager for macOS (launchd) or Linux (systemd).
    Raises RuntimeError on unsupported platforms.
    """
    system = platform.system()
    if system == "Darwin":
        from agent_cli.install.launchd import manager  # noqa: PLC0415

        return manager
    if system == "Linux":
        from agent_cli.install.systemd import manager  # noqa: PLC0415

        return manager
    msg = (
        f"Unsupported platform: {system}\n\n"
        "The daemon command manages system services using launchd (macOS) or\n"
        "systemd (Linux). Windows is not currently supported.\n\n"
        "Alternatives:\n"
        "  - Run servers manually: agent-cli server <name>\n"
        "  - Use Docker: docker run -p 10300:10300 agent-cli server whisper\n\n"
        "See: https://agent-cli.nijho.lt/installation/docker/"
    )
    raise RuntimeError(msg)
