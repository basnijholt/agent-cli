"""Handles loading and parsing of the agent-cli configuration file."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .utils import console

CONFIG_PATH = Path.home() / ".config" / "agent-cli" / "config.toml"
CONFIG_PATH_2 = Path("agent-cli-config.toml")


def _replace_dashed_keys_recursive(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace dashed keys with underscores in a dictionary."""
    new_dict = {}
    for k, v in d.items():
        new_key = k.replace("-", "_")
        if isinstance(v, dict):
            new_dict[new_key] = _replace_dashed_keys_recursive(v)
        else:
            new_dict[new_key] = v
    return new_dict


def load_config(config_path_str: str | None = None) -> dict[str, Any]:
    """Load the TOML configuration file and process it for nested structures."""
    # Determine which config path to use
    if config_path_str:
        config_path = Path(config_path_str)
    elif CONFIG_PATH.exists():
        config_path = CONFIG_PATH
    elif CONFIG_PATH_2.exists():
        config_path = CONFIG_PATH_2
    else:
        return {}

    # Try to load and process the config
    if config_path.exists():
        try:
            with config_path.open("rb") as f:
                cfg = tomllib.load(f)
                return _replace_dashed_keys_recursive(cfg)
        except tomllib.TOMLDecodeError as e:
            console.print(
                f"[bold red]Error parsing config file {config_path}: {e}[/bold red]",
            )
            return {}

    # Report error only if an explicit path was given
    if config_path_str:
        console.print(
            f"[bold red]Config file not found at {config_path_str}[/bold red]",
        )
    return {}
