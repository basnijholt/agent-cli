"""Tests for the transcribe agent."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.core import process

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


@patch("agent_cli.agents.transcribe.asr.create_transcriber")
@patch("agent_cli.agents.transcribe.process.pid_file_context")
@patch("agent_cli.agents.transcribe.setup_devices")
def test_transcribe_agent(
    mock_setup_devices: MagicMock,
    mock_pid_context: MagicMock,
    mock_create_transcriber: MagicMock,
) -> None:
    """Test the transcribe agent."""
    mock_transcriber = AsyncMock(return_value="hello")
    mock_create_transcriber.return_value = mock_transcriber
    mock_setup_devices.return_value = (0, "mock_device", None)
    with patch("pyperclip.copy") as mock_copy, patch("pyperclip.paste", return_value=""):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "--asr-provider",
                "wyoming",
                "--openai-api-key",
                "test",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_pid_context.assert_called_once()
    mock_create_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()
    mock_copy.assert_called_once_with("hello")


@patch("agent_cli.agents.transcribe.asr.create_transcriber")
@patch("agent_cli.agents.transcribe.setup_devices")
def test_transcribe_start_writes_pid_before_audio_setup(
    mock_setup_devices: MagicMock,
    mock_create_transcriber: MagicMock,
    tmp_path: Path,
) -> None:
    """Explicit start should enter the PID context before audio setup can block."""
    events: list[str] = []
    mock_transcriber = AsyncMock(return_value="hello")
    mock_create_transcriber.return_value = mock_transcriber

    def setup_devices(*_args: object, **_kwargs: object) -> tuple[int, str, None]:
        events.append("setup_devices")
        return (0, "mock_device", None)

    @contextmanager
    def pid_file_context(process_name: str) -> Generator[Path, None, None]:
        events.append(f"pid_enter:{process_name}")
        yield tmp_path / "transcribe.pid"
        events.append(f"pid_exit:{process_name}")

    mock_setup_devices.side_effect = setup_devices
    with (
        patch("agent_cli.agents.transcribe.process.pid_file_context", pid_file_context),
        patch("pyperclip.copy"),
        patch("pyperclip.paste", return_value=""),
    ):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "--start",
                "--asr-provider",
                "wyoming",
                "--openai-api-key",
                "test",
            ],
        )

    assert result.exit_code == 0, result.output
    assert events[0] == "pid_enter:transcribe"
    assert events[1] == "setup_devices"


@patch("agent_cli.agents.transcribe.process.stop_process")
def test_transcribe_stop(mock_stop_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_stop_process.return_value = process.StopProcessResult(
        process_name="transcribe",
        was_running=True,
        status=process.ProcessStatus("transcribe", running=False, pid=None),
        stale_cleaned=False,
    )
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "Transcribe stopped" in result.stdout
    mock_stop_process.assert_called_once_with("transcribe", wait_for_start_seconds=0.0)


@patch("agent_cli.agents.transcribe.process.stop_process")
def test_transcribe_stop_not_running(mock_stop_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_stop_process.return_value = process.StopProcessResult(
        process_name="transcribe",
        was_running=False,
        status=process.ProcessStatus("transcribe", running=False, pid=None),
        stale_cleaned=False,
    )
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "No transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process.get_process_status")
def test_transcribe_status_running(mock_get_process_status: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_get_process_status.return_value = process.ProcessStatus(
        process_name="transcribe",
        running=True,
        pid=123,
    )
    result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process.get_process_status")
def test_transcribe_status_not_running(mock_get_process_status: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_get_process_status.return_value = process.ProcessStatus(
        process_name="transcribe",
        running=False,
        pid=None,
    )
    result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is not running" in result.stdout


def test_transcribe_status_json_running() -> None:
    """Transcribe status should support machine-readable process state."""
    with patch(
        "agent_cli.agents.transcribe.process.get_process_status",
        return_value=process.ProcessStatus(
            process_name="transcribe",
            running=True,
            pid=123,
            stale_cleaned=False,
        ),
    ):
        result = runner.invoke(app, ["transcribe", "--status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "action": "status",
        "process": "transcribe",
        "running": True,
        "status": "running",
        "pid": 123,
        "stale_cleaned": False,
    }


def test_transcribe_stop_json_cleans_stale_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping with a stale PID should clean it and report stopped as JSON."""
    monkeypatch.setattr(process, "PID_DIR", tmp_path)
    pid_file = process._get_pid_file("transcribe")
    pid_file.write_text("999999")

    with patch("agent_cli.core.process._is_pid_running", return_value=False):
        result = runner.invoke(app, ["transcribe", "--stop", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "stop"
    assert payload["process"] == "transcribe"
    assert payload["running"] is False
    assert payload["status"] == "stopped"
    assert payload["pid"] is None
    assert payload["was_running"] is False
    assert payload["stale_cleaned"] is True
    assert not pid_file.exists()
