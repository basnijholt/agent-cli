"""Google Gemini CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Gemini(CodingAgent):
    """Google Gemini CLI coding agent."""

    name = "gemini"
    command = "gemini"
    install_url = "https://github.com/google-gemini/gemini-cli"
    detect_process_name = "gemini"

    def prompt_args(self, prompt: str) -> list[str]:
        """Return prompt using -p flag.

        Gemini CLI uses -p for non-interactive prompts:
        `gemini -p "your prompt here"`

        See: https://github.com/google-gemini/gemini-cli README
        """
        return ["-p", prompt]
