"""GitHub Copilot CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Copilot(CodingAgent):
    """GitHub Copilot CLI coding agent."""

    name = "copilot"
    command = "copilot"
    install_url = "https://github.com/github/copilot-cli"
    detect_process_name = "copilot"
