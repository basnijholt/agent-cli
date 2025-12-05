"""Process management utilities for Agent CLI tools."""

from __future__ import annotations

import os
import signal
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

# Default location for PID files
PID_DIR = Path.home() / ".cache" / "agent-cli"
_WAIT_INTERVAL_SECONDS = 0.1


def _get_pid_file(process_name: str) -> Path:
    """Get the path to the PID file for a given process name."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{process_name}.pid"


def _get_stop_file(process_name: str) -> Path:
    """Get the path to the stop file for a given process name."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{process_name}.stop"


def check_stop_file(process_name: str) -> bool:
    """Check if a stop file exists (used for cross-process signaling on Windows)."""
    return _get_stop_file(process_name).exists()


def clear_stop_file(process_name: str) -> None:
    """Remove the stop file for the given process."""
    stop_file = _get_stop_file(process_name)
    if stop_file.exists():
        stop_file.unlink()


def _is_pid_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if sys.platform == "win32":
        # On Windows, use ctypes to check process existence
        import ctypes  # noqa: PLC0415

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        process = kernel32.OpenProcess(synchronize, 0, pid)
        if process:
            kernel32.CloseHandle(process)
            return True
        return False
    # On Unix, use signal 0 to check if process exists
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _wait_for_exit(process_name: str, timeout: float) -> bool:
    """Wait for a process to exit within the given timeout."""
    if timeout <= 0:
        return not is_process_running(process_name)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_process_running(process_name):
            return True
        time.sleep(_WAIT_INTERVAL_SECONDS)
    return not is_process_running(process_name)


def _send_signal(pid: int, signum: signal.Signals) -> bool:
    """Attempt to deliver a signal to the process."""
    if sys.platform == "win32":
        # On Windows, os.kill only supports SIGTERM (calls TerminateProcess)
        # SIGINT/SIGBREAK don't work via os.kill for arbitrary processes
        import ctypes  # noqa: PLC0415

        kernel32 = ctypes.windll.kernel32
        process_terminate = 0x0001
        handle = kernel32.OpenProcess(process_terminate, 0, pid)
        if not handle:
            return False
        result = kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)
        return bool(result)

    try:
        os.kill(pid, signum)
        return True
    except ProcessLookupError:
        # Process already exited. Treat as delivered.
        return True
    except (PermissionError, OSError):
        return False


def _termination_sequence() -> list[tuple[signal.Signals, float]]:
    """Return an ordered list of signals and grace periods to attempt."""
    if sys.platform == "win32":
        # On Windows we use TerminateProcess directly, signal choice is ignored
        return [(signal.SIGTERM, 0.5)]

    return [
        (signal.SIGINT, 0.5),
        (signal.SIGTERM, 0.5),
        (signal.SIGKILL, 0.5),
    ]


def _terminate_process(pid: int, process_name: str) -> bool:
    """Attempt to terminate the process using escalating signals."""
    for signum, wait_time in _termination_sequence():
        if not _send_signal(pid, signum):
            continue
        if _wait_for_exit(process_name, wait_time):
            return True
    return not is_process_running(process_name)


def _get_running_pid(process_name: str) -> int | None:
    """Get PID if process is running, None otherwise. Cleans up stale files."""
    pid_file = _get_pid_file(process_name)

    if not pid_file.exists():
        return None

    try:
        with pid_file.open() as f:
            pid = int(f.read().strip())

        # Check if process is actually running
        if _is_pid_running(pid):
            return pid

    except (FileNotFoundError, ValueError):
        pass

    # Clean up stale/invalid PID file
    if pid_file.exists():
        pid_file.unlink()
    return None


def is_process_running(process_name: str) -> bool:
    """Check if a process is currently running."""
    return _get_running_pid(process_name) is not None


def read_pid_file(process_name: str) -> int | None:
    """Read PID from file if process is running."""
    return _get_running_pid(process_name)


def kill_process(process_name: str) -> bool:
    """Kill a process by name.

    Returns True if the process was stopped (or a stale PID file was cleaned up).
    Returns False if no PID exists or the process could not be terminated.

    On Windows, creates a stop file first to allow graceful shutdown before
    falling back to forceful termination.
    """
    pid_file = _get_pid_file(process_name)

    # If no PID file exists at all, nothing to do
    if not pid_file.exists():
        return False

    # Check if we have a running process
    pid = _get_running_pid(process_name)

    # If _get_running_pid returned None but file existed, it cleaned up a stale file
    if pid is None:
        return True  # Cleanup of stale file is success

    # On Windows, create stop file first to allow graceful shutdown
    # The running process checks this file and exits cleanly
    if sys.platform == "win32":
        _get_stop_file(process_name).touch()
        # Give process time to notice the stop file and shut down gracefully
        if _wait_for_exit(process_name, timeout=3.0):
            clear_stop_file(process_name)
            if pid_file.exists():
                pid_file.unlink()
            return True
        # Process didn't stop gracefully, fall through to forceful termination

    if not _terminate_process(pid, process_name):
        clear_stop_file(process_name)
        return False

    clear_stop_file(process_name)
    if pid_file.exists():
        pid_file.unlink()

    return True


@contextmanager
def pid_file_context(process_name: str) -> Generator[Path, None, None]:
    """Context manager for PID file lifecycle.

    Creates PID file on entry, cleans up on exit.
    Exits with error if process already running.
    """
    if is_process_running(process_name):
        existing_pid = _get_running_pid(process_name)
        print(f"Process {process_name} is already running (PID: {existing_pid})")
        sys.exit(1)

    # Clear any stale stop file from previous run
    clear_stop_file(process_name)

    pid_file = _get_pid_file(process_name)
    with pid_file.open("w") as f:
        f.write(str(os.getpid()))

    try:
        yield pid_file
    finally:
        if pid_file.exists():
            pid_file.unlink()
        clear_stop_file(process_name)
