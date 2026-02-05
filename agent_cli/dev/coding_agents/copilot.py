"""GitHub Copilot CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Copilot(CodingAgent):
    """GitHub Copilot CLI coding agent."""

    name = "copilot"
    command = "copilot"
    install_url = "https://github.com/github/copilot-cli"
    detect_process_name = "copilot"

    def prompt_args(self, prompt: str) -> list[str]:
        """Return prompt using --prompt flag.

        Copilot CLI uses -p/--prompt for initial prompts:
        `copilot --prompt "your prompt here"`

        See: https://github.com/github/copilot-cli
        """
        return ["--prompt", prompt]
