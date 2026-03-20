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


def get_dev_config() -> dict[str, Any]:
    """Return the `[dev]` config table for the current CLI invocation."""
    dev_config = get_runtime_config().get("dev", {})
    return dev_config if isinstance(dev_config, dict) else {}


def get_dev_table(name: str) -> dict[str, Any]:
    """Return a merged `[dev.<name>]` table from nested or flattened config."""
    result: dict[str, Any] = {}

    nested = get_dev_config().get(name)
    if isinstance(nested, dict):
        result.update(nested)

    flat = get_runtime_config().get(f"dev.{name}")
    if isinstance(flat, dict):
        result.update(flat)

    return result


def get_dev_child_tables(name: str) -> dict[str, dict[str, Any]]:
    """Return merged `[dev.<name>.<child>]` tables keyed by child name."""
    result = {
        child: value for child, value in get_dev_table(name).items() if isinstance(value, dict)
    }

    prefix = f"dev.{name}."
    for key, value in get_runtime_config().items():
        if key.startswith(prefix) and isinstance(value, dict):
            result[key[len(prefix) :]] = value

    return result


def get_dev_child_table(name: str, child: str) -> dict[str, Any]:
    """Return a single merged `[dev.<name>.<child>]` table."""
    return get_dev_child_tables(name).get(child, {})
