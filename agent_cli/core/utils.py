"""Utility functions for agent CLI operations."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import (
    AbstractContextManager,
    asynccontextmanager,
    contextmanager,
    nullcontext,
    suppress,
)
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.status import Status
from rich.table import Table
from rich.text import Text

from . import process

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Generator, Iterator
    from datetime import timedelta
    from logging import Handler
    from pathlib import Path

console = Console()
err_console = Console(stderr=True)


def enable_json_mode() -> None:
    """Silence Rich console output for JSON mode.

    Call this early in a command when --json flag is set.
    All subsequent console.print() calls will be silenced.
    """
    console.quiet = True


class InteractiveStopEvent:
    """A stop event with reset capability for chat agents."""

    def __init__(self, process_name: str | None = None) -> None:
        """Initialize the chat stop event."""
        self._event = asyncio.Event()
        self._sigint_count = 0
        self._ctrl_c_pressed = False
        self._process_name = process_name

    def is_set(self) -> bool:
        """Check if the stop event is set or stop file exists (Windows)."""
        if self._event.is_set():
            return True
        # On Windows, also check for stop file (cross-process signaling)
        if self._process_name is not None and process.check_stop_file(self._process_name):
            self._event.set()  # Set the event so subsequent checks are fast
            return True
        return False

    def set(self) -> None:
        """Set the stop event."""
        self._event.set()

    def clear(self) -> None:
        """Clear the stop event and reset interrupt count for next iteration."""
        self._event.clear()
        self._sigint_count = 0
        self._ctrl_c_pressed = False

    def increment_sigint_count(self) -> int:
        """Increment and return the SIGINT count."""
        self._sigint_count += 1
        self._ctrl_c_pressed = True
        return self._sigint_count

    @property
    def ctrl_c_pressed(self) -> bool:
        """Check if Ctrl+C was pressed."""
        return self._ctrl_c_pressed


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text to a file atomically using a temporary file and rename."""
    # Create a temp file in the same directory to ensure atomic rename works
    temp_file = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temp_file.write_text(content, encoding=encoding)
        temp_file.replace(path)
    except Exception:
        if temp_file.exists():
            temp_file.unlink()
        raise


def format_timedelta_to_ago(td: timedelta) -> str:
    """Format a timedelta into a human-readable 'ago' string."""
    seconds = int(td.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    return f"{seconds} second{'s' if seconds != 1 else ''} ago"


def format_short_timedelta(delta: timedelta) -> str:
    """Format a timedelta into a compact 'Xm Ys' string."""
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < SECONDS_PER_MINUTE:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, SECONDS_PER_MINUTE)
    if minutes < MINUTES_PER_HOUR:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours, minutes = divmod(minutes, MINUTES_PER_HOUR)
    if hours < HOURS_PER_DAY:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, HOURS_PER_DAY)
    return f"{days}d {hours}h"


def iter_lines_from_file_end(path: Path, chunk_size: int) -> Iterator[str]:
    """Yield lines from the end of a file in reverse order."""
    if chunk_size <= 0:
        msg = "chunk_size must be positive"
        raise ValueError(msg)

    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        position = file.tell()
        buffer = b""

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            chunk = file.read(read_size)
            buffer = chunk + buffer

            while True:
                newline_idx = buffer.rfind(b"\n")
                if newline_idx == -1:
                    break
                line_bytes = buffer[newline_idx + 1 :].strip()
                buffer = buffer[:newline_idx]
                if line_bytes:
                    yield line_bytes.decode("utf-8", errors="ignore")

            if position == 0:
                final_line = buffer.strip()
                if final_line:
                    yield final_line.decode("utf-8", errors="ignore")
                buffer = b""


def parse_json_line(line: str) -> dict[str, Any] | None:
    """Parse a JSON line and return a dictionary, or None if invalid."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _create_spinner(text: str, style: str) -> Spinner:
    """Creates a default spinner."""
    return Spinner("dots", text=Text(text, style=style))


def create_status(text: str, style: str = "bold yellow") -> Status:
    """Creates a default status with spinner."""
    spinner_text = Text(text, style=style)
    return Status(spinner_text, console=console, spinner="dots")


def print_input_panel(
    text: str,
    title: str = "Input",
    subtitle: str = "",
    style: str = "bold blue",
) -> None:
    """Prints a panel with the input text."""
    console.print(Panel(text, title=title, subtitle=subtitle, border_style=style))


def print_output_panel(
    text: str,
    title: str = "Output",
    subtitle: str = "",
    style: str = "bold green",
) -> None:
    """Prints a panel with the output text."""
    console.print(Panel(text, title=title, subtitle=subtitle, border_style=style))


def print_error_message(message: str, suggestion: str | None = None) -> None:
    """Prints an error message in a panel with rich markup support."""
    error_text = Text.from_markup(message)
    if suggestion:
        error_text.append("\n\n")
        error_text.append(suggestion)
    console.print(Panel(error_text, title="Error", border_style="bold red"))


def print_with_style(message: str, style: str = "bold green") -> None:
    """Prints a status message."""
    console.print(f"[{style}]{message}[/{style}]")


def print_device_index(input_device_index: int | None, input_device_name: str | None) -> None:
    """Prints the device index."""
    if input_device_index is not None:
        name = input_device_name or "Unknown Device"
        print_with_style(f"Using {name} device with index {input_device_index}")


def get_clipboard_text(*, quiet: bool = False) -> str | None:
    """Get text from clipboard, with an optional status message."""
    import pyperclip  # noqa: PLC0415

    text = pyperclip.paste()
    if not text:
        if not quiet:
            print_with_style("Clipboard is empty.", style="yellow")
        return None
    return text


@contextmanager
def signal_handling_context(
    logger: logging.Logger,
    quiet: bool = False,
    process_name: str | None = None,
) -> Generator[InteractiveStopEvent, None, None]:
    """Context manager for graceful signal handling with double Ctrl+C support.

    Sets up handlers for SIGINT (Ctrl+C) and SIGTERM (kill command):
    - First Ctrl+C: Graceful shutdown with warning message
    - Second Ctrl+C: Force exit with code 130
    - SIGTERM: Immediate graceful shutdown

    On Windows, also monitors for a stop file (cross-process signaling).

    Args:
        logger: Logger instance for recording events
        quiet: Whether to suppress console output
        process_name: Optional process name for stop file monitoring (Windows)

    Yields:
        stop_event: InteractiveStopEvent that gets set when shutdown is requested

    """
    stop_event = InteractiveStopEvent(process_name=process_name)

    def _sigint_handler() -> None:
        sigint_count = stop_event.increment_sigint_count()

        if sigint_count == 1:
            logger.info("First Ctrl+C received. Processing transcription.")
            # The Ctrl+C message will be shown by the ASR function
            stop_event.set()
        else:
            logger.info("Second Ctrl+C received. Force exiting.")
            if not quiet:
                console.print("\n[red]Force exit![/red]")
            sys.exit(130)  # Standard exit code for Ctrl+C

    def _sigterm_handler() -> None:
        logger.info("SIGTERM received. Stopping process.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    restore_handlers: dict[signal.Signals, Any] = {}

    def _register_async_handlers() -> None:
        """Register signal handlers using asyncio loop (Unix)."""
        loop.add_signal_handler(signal.SIGINT, _sigint_handler)
        loop.add_signal_handler(signal.SIGTERM, _sigterm_handler)

    def _register_sync_handlers() -> None:
        """Register signal handlers using standard signal module (Windows)."""
        logger.debug("Using sync signal handlers (Windows platform).")

        def register(signum: signal.Signals, handler: Any) -> None:
            restore_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, handler)

        register(signal.SIGINT, lambda *_: _sigint_handler())
        register(signal.SIGTERM, lambda *_: _sigterm_handler())

    if sys.platform == "win32":
        _register_sync_handlers()
    else:
        _register_async_handlers()

    try:
        yield stop_event
    finally:
        for signum, previous in restore_handlers.items():
            signal.signal(signum, previous)


def stop_or_status_or_toggle(
    process_name: str,
    which: str,
    stop: bool,
    status: bool,
    toggle: bool,
    *,
    quiet: bool = False,
) -> bool:
    """Handle process control for a given process name."""
    if stop:
        if process.kill_process(process_name):
            if not quiet:
                print_with_style(f"✅ {which.capitalize()} stopped.")
        elif not quiet:
            print_with_style(f"⚠️  No {which} is running.", style="yellow")
        return True

    if status:
        if process.is_process_running(process_name):
            pid = process.read_pid_file(process_name)
            if not quiet:
                print_with_style(f"✅ {which.capitalize()} is running (PID: {pid}).")
        elif not quiet:
            print_with_style(f"⚠️ {which.capitalize()} is not running.", style="yellow")
        return True

    if toggle:
        if process.is_process_running(process_name):
            if process.kill_process(process_name) and not quiet:
                print_with_style(f"✅ {which.capitalize()} stopped.")
            return True
        if not quiet:
            print_with_style(f"⚠️ {which.capitalize()} is not running.", style="yellow")

    return False


def maybe_live(use_live: bool) -> AbstractContextManager[Live | None]:
    """Create a live context manager if use_live is True."""
    if use_live:
        return Live(_create_spinner("Initializing", "blue"), console=console, transient=True)
    return nullcontext()


@asynccontextmanager
async def live_timer(
    live: Live,
    base_message: str,
    *,
    quiet: bool = False,
    style: str = "blue",
    stop_event: InteractiveStopEvent | None = None,
) -> AsyncGenerator[None, None]:
    """Async context manager that automatically manages a timer for a Live display.

    Args:
        live: Live instance to update (or None to do nothing)
        base_message: Base message to display
        style: Rich style for the text
        quiet: If True, don't show any display
        stop_event: Optional stop event to check for Ctrl+C

    Usage:
        async with live_timer(live, "🤖 Processing", style="bold yellow"):
            # Do your work here, timer updates automatically
            await some_operation()

    """
    if quiet:
        yield
        return

    # Start the timer task
    start_time = time.monotonic()

    async def update_timer() -> None:
        """Update the timer display."""
        while True:
            elapsed = time.monotonic() - start_time

            # Check if Ctrl+C was pressed
            if stop_event and stop_event.ctrl_c_pressed:
                ctrl_c_text = Text(
                    "Ctrl+C pressed. Processing transcription... (Press Ctrl+C again to force exit)",
                    style="yellow",
                )
                live.update(ctrl_c_text)
            else:
                spinner = _create_spinner(f"{base_message}... ({elapsed:.1f}s)", style)
                live.update(spinner)

            await asyncio.sleep(0.1)

    timer_task = asyncio.create_task(update_timer())

    try:
        yield
    finally:
        # Clean up timer task automatically
        timer_task.cancel()
        with suppress(asyncio.CancelledError):
            await timer_task
        if not quiet:
            live.update("")


def setup_logging(log_level: str, log_file: str | None, *, quiet: bool) -> None:
    """Sets up logging based on parsed arguments."""
    handlers: list[Handler] = []
    if not quiet:
        handlers.append(logging.StreamHandler())
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w"))

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


async def manage_send_receive_tasks(
    send_task_coro: Coroutine,
    receive_task_coro: Coroutine,
    *,
    return_when: str = asyncio.ALL_COMPLETED,
) -> tuple[asyncio.Task, asyncio.Task]:
    """Manage send and receive tasks with proper cancellation.

    Args:
        send_task_coro: Send task coroutine
        receive_task_coro: Receive task coroutine
        return_when: When to return (e.g., asyncio.ALL_COMPLETED)

    Returns:
        Tuple of (send_task, receive_task) - both completed or cancelled

    """
    send_task = asyncio.create_task(send_task_coro)
    recv_task = asyncio.create_task(receive_task_coro)

    _done, pending = await asyncio.wait(
        [send_task, recv_task],
        return_when=return_when,
    )

    # Cancel any pending tasks
    for task in pending:
        task.cancel()

    return send_task, recv_task


def print_command_line_args(
    args: dict[str, str | int | bool | None],
) -> None:
    """Print command line arguments in a formatted way."""
    from agent_cli import opts  # noqa: PLC0415

    table = Table(title="Command Line Arguments", show_header=True, header_style="bold magenta")
    table.add_column("Parameter", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    table.add_column("Type", style="dim")

    sorted_args = sorted(args.items())
    categories: dict[str, list[tuple[str, str | int | bool | None]]] = {}

    for key, value in sorted_args:
        if key == "ctx":
            continue
        try:
            category = getattr(opts, key.upper()).rich_help_panel
        except AttributeError:
            category = "Other"

        if category not in categories:
            categories[category] = []
        categories[category].append((key, value))

    sorted_categories = sorted(categories.items())
    for category, items in sorted_categories:
        if not items:
            continue
        # Add a separator row for the category
        table.add_row(f"[bold yellow]── {category} ──[/bold yellow]", "", "")

        for key, value in items:
            if value is None:
                formatted_value = "[dim]None[/dim]"
            elif isinstance(value, bool):
                formatted_value = "[green]✓[/green]" if value else "[red]✗[/red]"
            elif isinstance(value, str) and not value:
                formatted_value = "[dim]<empty>[/dim]"
            else:
                formatted_value = str(value)

            type_name = type(value).__name__
            if value is None:
                type_name = "NoneType"

            table.add_row(key, formatted_value, f"[dim]{type_name}[/dim]")

    # Print the table
    console.print()
    console.print(table)
    console.print()
