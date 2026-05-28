"""Process management utilities for Agent CLI tools."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Generator

# Store the original process title before any modifications
_original_proctitle: str | None = None


class _PidInfo(NamedTuple):
    pid: int
    uses_lock: bool


class ProcessStatus(NamedTuple):
    """Current state of a managed Agent CLI process."""

    process_name: str
    running: bool
    pid: int | None
    stale_cleaned: bool = False


class StopProcessResult(NamedTuple):
    """Result of a stop request for a managed Agent CLI process."""

    process_name: str
    was_running: bool
    status: ProcessStatus
    stale_cleaned: bool = False


def _default_pid_dir() -> Path:
    """Return local runtime dir for process control files."""
    if runtime_dir := os.environ.get("AGENTCLI_RUNTIME_DIR"):
        return Path(runtime_dir)

    if xdg_runtime_dir := os.environ.get("XDG_RUNTIME_DIR"):
        return Path(xdg_runtime_dir) / "agent-cli"

    if os.name == "posix":
        return Path(tempfile.gettempdir()) / f"agent-cli-{os.getuid()}"

    if local_app_data := os.environ.get("LOCALAPPDATA"):
        return Path(local_app_data) / "agent-cli" / "runtime"

    return Path(tempfile.gettempdir()) / "agent-cli-runtime"


# Default location for PID files and process locks.
PID_DIR = _default_pid_dir()


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


def _get_lock_file(process_name: str) -> Path:
    """Get the path to the process lock file for a given process name."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{process_name}.lock"


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
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _supports_process_locks() -> bool:
    """Return whether this platform supports POSIX advisory locks."""
    return sys.platform != "win32"


def _acquire_process_lock(process_name: str) -> int | None:
    """Try to acquire the per-process lock. Return fd when held."""
    if not _supports_process_locks():
        return None

    import fcntl  # noqa: PLC0415

    lock_file = _get_lock_file(process_name)
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except OSError:
        os.close(fd)
        raise
    return fd


def _release_process_lock(lock_fd: int | None) -> None:
    """Release a lock fd returned by _acquire_process_lock."""
    if lock_fd is None:
        return

    import fcntl  # noqa: PLC0415

    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)


def _is_process_lock_held(process_name: str) -> bool:
    """Return True when another process still owns the lock."""
    if not _supports_process_locks():
        return True

    lock_fd = _acquire_process_lock(process_name)
    if lock_fd is None:
        return True

    _release_process_lock(lock_fd)
    return False


def _legacy_pid_info(raw: str) -> _PidInfo | None:
    """Parse a legacy numeric PID file."""
    try:
        return _PidInfo(pid=int(raw), uses_lock=False)
    except ValueError:
        return None


def _pid_info_from_payload(process_name: str, payload: object) -> _PidInfo | None:
    """Parse JSON PID metadata."""
    if isinstance(payload, int):
        return _PidInfo(pid=payload, uses_lock=False)

    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("process_name") != process_name
    ):
        return None

    try:
        pid = int(payload["pid"])
    except (KeyError, TypeError, ValueError):
        return None

    return _PidInfo(pid=pid, uses_lock=True)


def _read_pid_info(process_name: str) -> _PidInfo | None:
    """Read either current JSON PID metadata or a legacy numeric PID file."""
    pid_file = _get_pid_file(process_name)
    try:
        raw = pid_file.read_text().strip()
    except FileNotFoundError:
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _legacy_pid_info(raw)

    return _pid_info_from_payload(process_name, payload)


def _write_pid_info(process_name: str) -> None:
    """Write PID metadata for the current process."""
    pid_file = _get_pid_file(process_name)
    payload = {
        "version": 1,
        "process_name": process_name,
        "pid": os.getpid(),
        "created_at": time.time(),
    }
    pid_file.write_text(json.dumps(payload, sort_keys=True))


def _cleanup_process_files(process_name: str) -> None:
    """Remove stale process control files."""
    pid_file = _get_pid_file(process_name)
    if pid_file.exists():
        pid_file.unlink()
    clear_stop_file(process_name)


def get_process_status(process_name: str) -> ProcessStatus:
    """Return process state and deterministically clean stale control files."""
    if not _get_pid_file(process_name).exists():
        return ProcessStatus(process_name=process_name, running=False, pid=None)

    pid_info = _read_pid_info(process_name)
    if pid_info is None:
        _cleanup_process_files(process_name)
        return ProcessStatus(
            process_name=process_name,
            running=False,
            pid=None,
            stale_cleaned=True,
        )

    if pid_info.uses_lock and _supports_process_locks() and not _is_process_lock_held(process_name):
        _cleanup_process_files(process_name)
        return ProcessStatus(
            process_name=process_name,
            running=False,
            pid=None,
            stale_cleaned=True,
        )

    if _is_pid_running(pid_info.pid):
        return ProcessStatus(process_name=process_name, running=True, pid=pid_info.pid)

    _cleanup_process_files(process_name)
    return ProcessStatus(
        process_name=process_name,
        running=False,
        pid=None,
        stale_cleaned=True,
    )


def _wait_for_process_start(
    process_name: str,
    *,
    wait_for_start_seconds: float,
    poll_interval: float,
) -> ProcessStatus:
    """Wait briefly for a just-launched process to write its PID file."""
    deadline = time.monotonic() + wait_for_start_seconds
    status = get_process_status(process_name)
    while not status.running and time.monotonic() < deadline:
        time.sleep(poll_interval)
        status = get_process_status(process_name)
    return status


def _signal_running_process(process_name: str, pid: int) -> None:
    """Signal a known-running process and clean control files if it exits."""
    stop_file = _get_stop_file(process_name)
    should_force_kill = sys.platform != "win32" and stop_file.exists()

    # On Windows, create stop file to signal graceful shutdown
    if sys.platform == "win32":
        stop_file.touch()

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
        _cleanup_process_files(process_name)
    elif not should_force_kill:
        stop_file.touch()


def stop_process(
    process_name: str,
    *,
    wait_for_start_seconds: float = 0.0,
    poll_interval: float = 0.1,
) -> StopProcessResult:
    """Stop a process by name and return the resulting process state."""
    initial_status = get_process_status(process_name)
    if not initial_status.running and wait_for_start_seconds > 0:
        initial_status = _wait_for_process_start(
            process_name,
            wait_for_start_seconds=wait_for_start_seconds,
            poll_interval=poll_interval,
        )

    if not initial_status.running or initial_status.pid is None:
        clear_stop_file(process_name)
        return StopProcessResult(
            process_name=process_name,
            was_running=False,
            status=initial_status,
            stale_cleaned=initial_status.stale_cleaned,
        )

    _signal_running_process(process_name, initial_status.pid)
    status = get_process_status(process_name)
    return StopProcessResult(
        process_name=process_name,
        was_running=True,
        status=status,
        stale_cleaned=initial_status.stale_cleaned or status.stale_cleaned,
    )


@contextmanager
def pid_file_context(process_name: str) -> Generator[Path, None, None]:
    """Context manager for PID file lifecycle.

    Creates PID file on entry, cleans up on exit.
    Exits with error if process already running.
    """
    lock_fd = _acquire_process_lock(process_name)
    if _supports_process_locks() and lock_fd is None:
        existing_status = get_process_status(process_name)
        print(f"Process {process_name} is already running (PID: {existing_status.pid})")
        sys.exit(1)

    if not _supports_process_locks():
        existing_status = get_process_status(process_name)
        if existing_status.running:
            print(f"Process {process_name} is already running (PID: {existing_status.pid})")
            sys.exit(1)

    if _supports_process_locks():
        pid_info = _read_pid_info(process_name)
        if pid_info and not pid_info.uses_lock and _is_pid_running(pid_info.pid):
            _release_process_lock(lock_fd)
            print(f"Process {process_name} is already running (PID: {pid_info.pid})")
            sys.exit(1)
        _cleanup_process_files(process_name)

    # Clear stale stop markers from previous runs.
    clear_stop_file(process_name)

    pid_file = _get_pid_file(process_name)
    _write_pid_info(process_name)

    try:
        yield pid_file
    finally:
        _cleanup_process_files(process_name)
        _release_process_lock(lock_fd)
