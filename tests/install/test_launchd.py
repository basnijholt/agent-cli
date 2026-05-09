"""Tests for macOS launchd service management."""

from __future__ import annotations

from pathlib import Path

from agent_cli.install.launchd import _generate_plist
from agent_cli.install.service_config import SERVICES


def test_generate_plist_sets_path_for_homebrew_bins() -> None:
    plist = _generate_plist(
        SERVICES["whisper"],
        Path("/opt/homebrew/bin/uv"),
        Path("/Users/test"),
        Path("/Users/test/Library/Logs/agent-cli-whisper"),
    )

    path = plist["EnvironmentVariables"]["PATH"]

    assert "/opt/homebrew/bin" in path.split(":")
    assert "/usr/local/bin" in path.split(":")
    assert path.endswith("/usr/bin:/bin:/usr/sbin:/sbin")
