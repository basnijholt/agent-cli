"""Aider AI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class Aider(CodingAgent):
    """Aider - AI pair programming in your terminal."""

    name = "aider"
    command = "aider"
    install_url = "https://aider.chat"
    detect_process_name = "aider"
