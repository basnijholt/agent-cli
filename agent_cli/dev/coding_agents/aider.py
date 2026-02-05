"""Aider AI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Aider(CodingAgent):
    """Aider - AI pair programming in your terminal."""

    name = "aider"
    command = "aider"
    install_url = "https://aider.chat"
    detect_process_name = "aider"

    def prompt_args(self, prompt: str) -> list[str]:
        """Return prompt using --message flag.

        Aider uses -m/--message for initial prompts:
        `aider --message "your prompt here"`

        See: https://aider.chat/docs/scripting.html
        """
        return ["--message", prompt]
