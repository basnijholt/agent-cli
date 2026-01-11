"""Zed editor adapter."""

from __future__ import annotations

from .base import Editor


class Zed(Editor):
    """Zed - A high-performance, multiplayer code editor."""

    name = "zed"
    command = "zed"
    install_url = "https://zed.dev"
    detect_env_vars = ("ZED_TERM",)
    detect_term_program = "zed"
