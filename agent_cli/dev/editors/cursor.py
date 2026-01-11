"""Cursor editor adapter."""

from __future__ import annotations

from .base import Editor


class Cursor(Editor):
    """Cursor - AI-first code editor."""

    name = "cursor"
    command = "cursor"
    install_url = "https://cursor.com"
    detect_env_vars = ("CURSOR_AGENT",)
    # No detect_term_program - not verified (Cursor is proprietary)
