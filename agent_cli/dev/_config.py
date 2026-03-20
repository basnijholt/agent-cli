"""Helpers for reading runtime dev configuration."""

from __future__ import annotations

from typing import Any

import click

from agent_cli.config import load_config


def get_runtime_config() -> dict[str, Any]:
    """Return the config dict active for the current CLI invocation."""
    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        if isinstance(ctx.obj, dict) and isinstance(ctx.obj.get("config"), dict):
            return ctx.obj["config"]
        ctx = ctx.parent
    return load_config(None)
