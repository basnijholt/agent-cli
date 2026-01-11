"""Sublime Text editor adapter."""

from __future__ import annotations

from .base import Editor


class SublimeText(Editor):
    """Sublime Text - A sophisticated text editor for code.

    Note: Sublime Text does not have a built-in integrated terminal.
    Terminal packages (like Terminus) may be used but don't set
    specific environment variables for detection.
    """

    name = "sublime"
    command = "subl"
    alt_commands = ("sublime_text", "sublime")
    install_url = "https://www.sublimetext.com"
    # No detect_term_program - Sublime has no native integrated terminal
