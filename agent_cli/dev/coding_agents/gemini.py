"""Google Gemini CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Gemini(CodingAgent):
    """Google Gemini CLI coding agent."""

    name = "gemini"
    command = "gemini"
    install_url = "https://github.com/google-gemini/gemini-cli"
    detect_process_name = "gemini"

    # Note: Gemini CLI's -p flag runs in non-interactive/headless mode (exits after
    # response), unlike Claude/Codex which stay interactive. We don't implement
    # prompt_args() here since the behavior differs from other agents.
    # See: https://google-gemini.github.io/gemini-cli/docs/cli/headless.html
