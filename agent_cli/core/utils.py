"""Utility functions for agent CLI operations."""

from __future__ import annotations

import asyncio
import logging
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
from typing import TYPE_CHECKING

import pyperclip
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.status import Status
from rich.text import Text

from . import process

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Generator
    from datetime import timedelta
    from logging import Handler

console = Console()


class InteractiveStopEvent:
    """A stop event with reset capability for chat agents."""

    def __init__(self) -> None:
        """Initialize the chat stop event."""
        self._event = asyncio.Event()
        self._sigint_count = 0
        self._ctrl_c_pressed = False

    def is_set(self) -> bool:
        """Check if the stop event is set."""
        return self._event.is_set()

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
    """Prints an error message in a panel."""
    error_text = Text(message)
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
) -> Generator[InteractiveStopEvent, None, None]:
    """Context manager for graceful signal handling with double Ctrl+C support.

    Sets up handlers for SIGINT (Ctrl+C) and SIGTERM (kill command):
    - First Ctrl+C: Graceful shutdown with warning message
    - Second Ctrl+C: Force exit with code 130
    - SIGTERM: Immediate graceful shutdown

    Args:
        logger: Logger instance for recording events
        quiet: Whether to suppress console output

    Yields:
        stop_event: InteractiveStopEvent that gets set when shutdown is requested

    """
    stop_event = InteractiveStopEvent()

    def sigint_handler() -> None:
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

    def sigterm_handler() -> None:
        logger.info("SIGTERM received. Stopping process.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, sigint_handler)
    loop.add_signal_handler(signal.SIGTERM, sigterm_handler)

    try:
        yield stop_event
    finally:
        # Signal handlers are automatically cleaned up when the event loop exits
        pass


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

    done, pending = await asyncio.wait(
        [send_task, recv_task],
        return_when=return_when,
    )

    # Cancel any pending tasks
    for task in pending:
        task.cancel()

    return send_task, recv_task
