"""Google Gemini CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Gemini(CodingAgent):
    """Google Gemini CLI coding agent."""

    name = "gemini"
    command = "gemini"
    install_url = "https://github.com/google-gemini/gemini-cli"
    detect_process_name = "gemini"
