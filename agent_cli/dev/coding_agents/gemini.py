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
        """Return prompt as positional argument.

        Gemini CLI accepts prompt as a positional argument:
        `gemini "your prompt here"`

        See: https://github.com/google-gemini/gemini-cli
        """
        return [prompt]
