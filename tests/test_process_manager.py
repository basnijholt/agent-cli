"""Tests for the process module."""

from __future__ import annotations

import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

from agent_cli.core import process


@pytest.fixture
def temp_pid_dir(monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Create a temporary directory for PID files during testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        monkeypatch.setattr(process, "PID_DIR", temp_path)
        yield temp_path


def test_get_pid_file(temp_pid_dir: Path) -> None:
    """Test PID file path generation."""
    pid_file = process._get_pid_file("test-process")
    assert pid_file == temp_pid_dir / "test-process.pid"
    assert temp_pid_dir.exists()


def test_is_process_running_no_file() -> None:
    """Test checking if a process is running when no PID file exists."""
    assert not process.is_process_running("nonexistent-process")


def test_is_process_running_invalid_pid() -> None:
    """Test checking if a process is running with invalid PID."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Write invalid PID
    pid_file.write_text("invalid")

    assert not process.is_process_running(process_name)
    # Should clean up invalid PID file
    assert not pid_file.exists()


def test_is_process_running_dead_process() -> None:
    """Test checking if a process is running with dead process PID."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Use a PID that's very unlikely to exist
    dead_pid = 999999
    pid_file.write_text(str(dead_pid))

    assert not process.is_process_running(process_name)
    # Should clean up stale PID file
    assert not pid_file.exists()


def test_is_process_running_current_process() -> None:
    """Test checking if a process is running with current process PID."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Write current process PID
    pid_file.write_text(str(os.getpid()))

    assert process.is_process_running(process_name)


def test_read_pid_file_no_file() -> None:
    """Test reading PID file when it doesn't exist."""
    assert process.read_pid_file("nonexistent-process") is None


def test_read_pid_file_current_process() -> None:
    """Test reading PID file with current process."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Write current process PID
    current_pid = os.getpid()
    pid_file.write_text(str(current_pid))

    assert process.read_pid_file(process_name) == current_pid


@pytest.mark.skipif(sys.platform == "win32", reason="os.kill(pid, 0) not used on Windows")
@patch("agent_cli.core.process._wait_for_exit", return_value=True)
@patch("os.kill")
def test_kill_process_success(
    mock_os_kill: MagicMock,
    mock_wait_for_exit: MagicMock,  # noqa: ARG001
) -> None:
    """Test successfully killing a process."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Write current process PID
    current_pid = os.getpid()
    pid_file.write_text(str(current_pid))

    result = process.kill_process(process_name)
    assert result is True
    mock_os_kill.assert_any_call(current_pid, 0)
    mock_os_kill.assert_any_call(current_pid, signal.SIGINT)
    assert not pid_file.exists()


def test_kill_process_not_running() -> None:
    """Test killing a process that is not running."""
    result = process.kill_process("nonexistent-process")
    assert result is False


@patch("os.kill", side_effect=ProcessLookupError)
def test_kill_process_already_dead(
    mock_os_kill: MagicMock,  # noqa: ARG001
) -> None:
    """Test killing a process that is already dead (stale PID file)."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Write a PID (doesn't matter if it's valid since we're mocking)
    pid_file.write_text("12345")

    result = process.kill_process(process_name)
    assert result is True
    assert not pid_file.exists()


@patch("agent_cli.core.process._wait_for_exit")
@patch("agent_cli.core.process._send_signal")
@patch("agent_cli.core.process._termination_sequence")
def test_kill_process_falls_back_to_stronger_signal(
    mock_sequence: MagicMock,
    mock_send_signal: MagicMock,
    mock_wait: MagicMock,
) -> None:
    """Ensure kill_process escalates signals until the process stops."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)
    current_pid = os.getpid()
    pid_file.write_text(str(current_pid))

    mock_sequence.return_value = [(signal.SIGINT, 0.1), (signal.SIGTERM, 0.1)]
    mock_send_signal.side_effect = [False, True]
    mock_wait.return_value = True

    assert process.kill_process(process_name)
    assert not pid_file.exists()
    assert mock_send_signal.call_args_list == [
        call(current_pid, signal.SIGINT),
        call(current_pid, signal.SIGTERM),
    ]
    mock_wait.assert_called_once_with(process_name, 0.1)


@patch("agent_cli.core.process._wait_for_exit", return_value=False)
@patch("agent_cli.core.process._send_signal", return_value=True)
@patch("agent_cli.core.process._termination_sequence", return_value=[(signal.SIGTERM, 0.1)])
def test_kill_process_failure_keeps_pid_file(
    mock_sequence: MagicMock,  # noqa: ARG001
    mock_send_signal: MagicMock,  # noqa: ARG001
    mock_wait: MagicMock,  # noqa: ARG001
) -> None:
    """If a process cannot be terminated, keep the PID file for future attempts."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)
    pid_file.write_text(str(os.getpid()))

    assert not process.kill_process(process_name)
    assert pid_file.exists()


def test_pid_file_context_success() -> None:
    """Test successful PID file context management."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Ensure no PID file exists initially
    if pid_file.exists():
        pid_file.unlink()
    assert not pid_file.exists()

    with process.pid_file_context(process_name) as returned_pid_file:
        # PID file should exist during context
        assert pid_file.exists()
        assert returned_pid_file == pid_file

        # PID file should contain current process ID
        with pid_file.open() as f:
            stored_pid = int(f.read().strip())
        assert stored_pid == os.getpid()

    # PID file should be cleaned up after context
    assert not pid_file.exists()


def test_pid_file_context_already_running() -> None:
    """Test PID file context when process is already running."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Create a PID file with current process ID to simulate running process
    pid_file.write_text(str(os.getpid()))

    try:
        with (  # noqa: PT012
            pytest.raises(SystemExit) as e,
            process.pid_file_context(process_name),
        ):
            msg = "Should not reach here"
            raise RuntimeError(msg)

        assert e.value.code == 1
    finally:
        # Clean up for other tests
        if pid_file.exists():
            pid_file.unlink()


def test_pid_file_context_exception_cleanup() -> None:
    """Test PID file is cleaned up even when exception occurs."""
    process_name = "test-process"
    pid_file = process._get_pid_file(process_name)

    # Ensure no PID file exists initially
    assert not pid_file.exists()

    with (  # noqa: PT012
        pytest.raises(ValueError, match="Test exception"),
        process.pid_file_context(process_name),
    ):
        # PID file should exist during context
        assert pid_file.exists()
        # Raise exception to test cleanup
        msg = "Test exception"
        raise ValueError(msg)

    # PID file should still be cleaned up after exception
    assert not pid_file.exists()
