"""OpenAI Codex CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Codex(CodingAgent):
    """OpenAI Codex CLI coding agent."""

    name = "codex"
    command = "codex"
    install_url = "https://github.com/openai/codex"
    detect_process_name = "codex"
