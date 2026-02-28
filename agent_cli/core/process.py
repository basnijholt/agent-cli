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
_FORCE_KILL_AFTER_SECONDS_DEFAULT = 20
_FORCE_KILL_AFTER_SECONDS_ENV = "AGENT_CLI_FORCE_KILL_AFTER_SECONDS"

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


def _get_force_stop_state_file(process_name: str) -> Path:
    """Get the force-stop state file path for a process."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{process_name}.stopstate"


def _read_force_stop_state(process_name: str) -> tuple[int, float] | None:
    """Read the last graceful-stop request metadata."""
    state_file = _get_force_stop_state_file(process_name)
    if not state_file.exists():
        return None

    try:
        raw = state_file.read_text(encoding="utf-8").strip()
        pid_str, ts_str = raw.split(maxsplit=1)
        return int(pid_str), float(ts_str)
    except (OSError, ValueError):
        state_file.unlink(missing_ok=True)
        return None


def _write_force_stop_state(process_name: str, *, pid: int, timestamp: float) -> None:
    """Persist graceful-stop request metadata for escalation checks."""
    state_file = _get_force_stop_state_file(process_name)
    state_file.write_text(f"{pid} {timestamp}", encoding="utf-8")


def _clear_force_stop_state(process_name: str) -> None:
    """Remove force-stop request metadata."""
    _get_force_stop_state_file(process_name).unlink(missing_ok=True)


def _force_kill_after_seconds() -> int:
    """Get SIGKILL escalation timeout from environment with sane defaults."""
    raw_value = os.getenv(_FORCE_KILL_AFTER_SECONDS_ENV)
    if raw_value is None:
        return _FORCE_KILL_AFTER_SECONDS_DEFAULT
    try:
        value = int(raw_value)
    except ValueError:
        return _FORCE_KILL_AFTER_SECONDS_DEFAULT
    return max(value, 0)


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
    _clear_force_stop_state(process_name)
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
        _clear_force_stop_state(process_name)
        return False

    # Check if we have a running process
    pid = _get_running_pid(process_name)

    # If _get_running_pid returned None but file existed, it cleaned up a stale file
    if pid is None:
        _clear_force_stop_state(process_name)
        return True

    force_after_seconds = _force_kill_after_seconds()
    stop_state = _read_force_stop_state(process_name)
    now = time.time()
    should_force_kill = (
        stop_state is not None
        and stop_state[0] == pid
        and force_after_seconds > 0
        and now - stop_state[1] >= force_after_seconds
        and sys.platform != "win32"
    )

    # On Windows, create stop file to signal graceful shutdown
    if sys.platform == "win32":
        _get_stop_file(process_name).touch()

    # Send SIGINT first; escalate to SIGKILL only when the same PID survives
    # repeated stop attempts beyond the configured timeout.
    stop_signal = signal.SIGKILL if should_force_kill else signal.SIGINT
    process_stopped = False
    try:
        os.kill(pid, stop_signal)
        # Wait for process to terminate
        for _ in range(10):  # 1 second max
            if not _is_pid_running(pid):
                process_stopped = True
                break
            time.sleep(0.1)
    except (ProcessLookupError, PermissionError):
        process_stopped = not _is_pid_running(pid)

    # Clean up
    if sys.platform == "win32":
        clear_stop_file(process_name)
    # Keep PID file if process is still alive so subsequent --status/--toggle
    # calls continue targeting the same process.
    if process_stopped:
        _clear_force_stop_state(process_name)
        if pid_file.exists():
            pid_file.unlink()
    elif not should_force_kill and (stop_state is None or stop_state[0] != pid):
        _write_force_stop_state(process_name, pid=pid, timestamp=now)

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
    _clear_force_stop_state(process_name)

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
        _clear_force_stop_state(process_name)
