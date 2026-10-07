"""Fresh-process checks for command loading on the recording startup path."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.timeout(45)
@pytest.mark.parametrize("command", ["transcribe", "voice-edit"])
def test_recording_help_does_not_load_unrelated_commands(command: str) -> None:
    """Recording must not pay for developer/server imports or option construction."""
    script = """
import json
import sys
from typer.testing import CliRunner
from agent_cli.cli import app
result = CliRunner().invoke(app, [sys.argv[1], '--help'])
print(json.dumps({'code': result.exit_code, 'output': result.stdout,
                  'modules': list(sys.modules)}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, command],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )
    report = json.loads(result.stdout)
    assert report["code"] == 0, report["output"]
    assert f"agent-cli {command}" in report["output"]
    assert "agent_cli.dev.cli" not in report["modules"]
    assert "agent_cli.server.cli" not in report["modules"]
    assert "agent_cli.agents.speakers" not in report["modules"]
    assert "agent_cli.agents.assistant" not in report["modules"]


@pytest.mark.timeout(45)
@pytest.mark.parametrize("mode", ["help", "completion", "docs"])
def test_fresh_help_completion_and_docs_keep_all_commands(mode: str) -> None:
    """Each discovery path must work before anything loads the command catalogue."""
    script = """
import json
import sys
from typer import Context
from typer.main import get_command
from typer.testing import CliRunner
from agent_cli.cli import app
if sys.argv[1] == 'docs':
    from agent_cli.docs_gen import _list_commands
    report = _list_commands()
elif sys.argv[1] == 'completion':
    group = get_command(app)
    report = [item.value for item in group.shell_complete(Context(group), 'trans')]
else:
    result = CliRunner().invoke(app, ['--help'])
    report = {'code': result.exit_code, 'output': result.stdout}
print(json.dumps(report))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, mode],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )
    report = json.loads(result.stdout)
    if mode == "help":
        assert report["code"] == 0, report["output"]
        assert "transcribe" in report["output"]
        assert "Development" in report["output"]
    elif mode == "completion":
        assert set(report) == {"transcribe", "transcribe-live"}
    else:
        assert {
            "transcribe",
            "voice-edit",
            "dev.new",
            "memory.proxy",
            "daemon.status",
            "server.asr",
            "server.whisper",
            "config.show",
            "install-services",
            "start-services",
        } <= set(report)


@pytest.mark.timeout(45)
@pytest.mark.parametrize("arguments", [["dev", "new"], ["memory", "proxy"], ["daemon", "status"]])
def test_fresh_nested_command_help(arguments: list[str]) -> None:
    """Selecting a nested command directly must load its options and parent group."""
    result = subprocess.run(
        [sys.executable, "-m", "agent_cli", *arguments, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )
    assert result.returncode == 0, result.stderr
    assert " ".join(arguments) in result.stdout
    assert "Options" in result.stdout
