"""Tests for macOS launchd service management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli.install.launchd import _generate_plist
from agent_cli.install.service_config import SERVICES

if TYPE_CHECKING:
    import pytest


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


def test_generate_plist_preserves_app_private_uv_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTCLI_APP_SUPPORT_DIR", "/Users/test/Library/Application Support/AgentCLI"
    )
    monkeypatch.setenv(
        "AGENTCLI_BUNDLED_UV", "/Applications/AgentCLI.app/Contents/Resources/bin/uv"
    )
    monkeypatch.setenv(
        "AGENTCLI_PACKAGE_SOURCE",
        "/Applications/AgentCLI.app/Contents/Resources/wheels/agent_cli-0.0.0-py3-none-any.whl",
    )
    monkeypatch.setenv("UV_CACHE_DIR", "/Users/test/Library/Application Support/AgentCLI/cache/uv")
    monkeypatch.setenv(
        "UV_PYTHON_INSTALL_DIR", "/Users/test/Library/Application Support/AgentCLI/uv/python"
    )
    monkeypatch.setenv("UV_TOOL_DIR", "/Users/test/Library/Application Support/AgentCLI/uv/tools")
    monkeypatch.setenv("UV_TOOL_BIN_DIR", "/Users/test/Library/Application Support/AgentCLI/bin")

    plist = _generate_plist(
        SERVICES["whisper"],
        Path("/Applications/AgentCLI.app/Contents/Resources/bin/uv"),
        Path("/Users/test"),
        Path("/Users/test/Library/Logs/agent-cli-whisper"),
    )

    environment = plist["EnvironmentVariables"]

    assert (
        environment["AGENTCLI_APP_SUPPORT_DIR"]
        == "/Users/test/Library/Application Support/AgentCLI"
    )
    assert (
        environment["AGENTCLI_BUNDLED_UV"] == "/Applications/AgentCLI.app/Contents/Resources/bin/uv"
    )
    assert (
        environment["AGENTCLI_PACKAGE_SOURCE"]
        == "/Applications/AgentCLI.app/Contents/Resources/wheels/agent_cli-0.0.0-py3-none-any.whl"
    )
    assert (
        environment["UV_CACHE_DIR"] == "/Users/test/Library/Application Support/AgentCLI/cache/uv"
    )
    assert (
        environment["UV_PYTHON_INSTALL_DIR"]
        == "/Users/test/Library/Application Support/AgentCLI/uv/python"
    )
    assert environment["UV_TOOL_DIR"] == "/Users/test/Library/Application Support/AgentCLI/uv/tools"
    assert environment["UV_TOOL_BIN_DIR"] == "/Users/test/Library/Application Support/AgentCLI/bin"
