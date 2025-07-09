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


def _get_pid_file(process_name: str) -> Path:
    """Get the path to the PID file for a given process name."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{process_name}.pid"


def _get_running_pid(process_name: str) -> int | None:
    """Get PID if process is running, None otherwise. Cleans up stale files."""
    pid_file = _get_pid_file(process_name)

    if not pid_file.exists():
        return None

    try:
        with pid_file.open() as f:
            pid = int(f.read().strip())

        # Check if process is actually running
        os.kill(pid, 0)
        return pid

    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
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
    """Kill a process by name. Returns True if killed or cleaned up, False if not found."""
    pid_file = _get_pid_file(process_name)

    # If no PID file exists at all, nothing to do
    if not pid_file.exists():
        return False

    # Check if we have a running process
    pid = _get_running_pid(process_name)

    # If _get_running_pid returned None but file existed, it cleaned up a stale file
    if pid is None:
        return True  # Cleanup of stale file is success

    # Kill the running process
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for process to terminate
        for _ in range(10):  # 1 second max
            if not is_process_running(process_name):
                break
            time.sleep(0.1)
    except (ProcessLookupError, PermissionError):
        pass  # Process dead or no permission - we'll clean up regardless

    # Clean up PID file
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

    pid_file = _get_pid_file(process_name)
    with pid_file.open("w") as f:
        f.write(str(os.getpid()))

    try:
        yield pid_file
    finally:
        if pid_file.exists():
            pid_file.unlink()
