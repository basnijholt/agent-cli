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

# Store the original process title before any modifications
_original_proctitle: str | None = None


def set_process_title(process_name: str) -> None:
    """Set the process title and thread name for identification in ps/htop/btop.

    Sets both:
    - Process title: 'agent-cli-{name} ({original})' - identifiable prefix + original command
    - Thread name: 'ag-{name}' (max 15 chars) - shown as program name in btop/htop

    The original command line is captured on first call and reused on subsequent
    calls to prevent nested titles like 'agent-cli-x (agent-cli-y (...))'.

    Args:
        process_name: The name of the process (e.g., 'transcribe', 'chat').

    """
    import setproctitle  # noqa: PLC0415

    global _original_proctitle

    # Capture the original command line only once, before any modification
    if _original_proctitle is None:
        _original_proctitle = setproctitle.getproctitle()

    # Set the full process title: identifiable prefix + original command for debugging
    setproctitle.setproctitle(f"agent-cli-{process_name} ({_original_proctitle})")

    # Set the thread name (program name in htop/btop, limited to 15 chars on Linux)
    # Use shorter prefix "ag-" to fit more of the command name
    thread_name = f"ag-{process_name}"[:15]
    setproctitle.setthreadtitle(thread_name)


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
        # On Windows, os.kill(pid, 0) would terminate the process!
        import psutil  # noqa: PLC0415

        return psutil.pid_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


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

    Returns True if killed or cleaned up, False if not found.
    On Windows, creates a stop file first to allow graceful shutdown.
    """
    pid_file = _get_pid_file(process_name)

    # If no PID file exists at all, nothing to do
    if not pid_file.exists():
        return False

    # Check if we have a running process
    pid = _get_running_pid(process_name)

    # If _get_running_pid returned None but file existed, it cleaned up a stale file
    if pid is None:
        return True

    # On Windows, create stop file to signal graceful shutdown
    if sys.platform == "win32":
        _get_stop_file(process_name).touch()

    # Send SIGINT for graceful shutdown
    try:
        os.kill(pid, signal.SIGINT)
        # Wait for process to terminate
        for _ in range(10):  # 1 second max
            if not is_process_running(process_name):
                break
            time.sleep(0.1)
    except (ProcessLookupError, PermissionError):
        pass  # Process dead or no permission - we'll clean up regardless

    # Clean up
    if sys.platform == "win32":
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

    # Clear any stale stop file from previous run (Windows only)
    if sys.platform == "win32":
        clear_stop_file(process_name)

    pid_file = _get_pid_file(process_name)
    with pid_file.open("w") as f:
        f.write(str(os.getpid()))

    try:
        yield pid_file
    finally:
        if pid_file.exists():
            pid_file.unlink()
        if sys.platform == "win32":
            clear_stop_file(process_name)
