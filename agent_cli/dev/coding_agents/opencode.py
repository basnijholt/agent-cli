"""OpenCode CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class OpenCode(CodingAgent):
    """OpenCode - AI coding assistant."""

    name = "opencode"
    command = "opencode"
    install_url = "https://opencode.ai"
    detect_env_var = "OPENCODE"
    detect_process_name = "opencode"
