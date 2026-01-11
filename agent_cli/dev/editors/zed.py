"""Zed editor adapter."""

from __future__ import annotations

from .base import Editor


class Zed(Editor):
    """Zed - A high-performance, multiplayer code editor.

    Detection via ZED_TERM=true (source code) or TERM_PROGRAM=zed (v0.145.0+).
    """

    name = "zed"
    command = "zed"
    install_url = "https://zed.dev"
    # ZED_TERM=true set in terminal.rs insert_zed_terminal_env()
    detect_env_vars = ("ZED_TERM",)
    # TERM_PROGRAM=zed added in v0.145.0 (PR #14213)
    detect_term_program = "zed"
