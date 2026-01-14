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
        """Return prompt using -i/--prompt-interactive flag.

        Gemini CLI uses -i for interactive mode with initial prompt:
        `gemini -i "your prompt here"`

        Note: -p/--prompt is non-interactive (exits after response).

        Evidence: `gemini --help` shows:
          -i, --prompt-interactive  Execute the provided prompt and continue
                                    in interactive mode
        """
        return ["-i", prompt]
