"""Tests for the utils module."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from agent_cli import utils


@pytest.mark.parametrize(
    ("td", "expected"),
    [
        (timedelta(seconds=5), "5 seconds ago"),
        (timedelta(minutes=5), "5 minutes ago"),
        (timedelta(hours=5), "5 hours ago"),
        (timedelta(days=5), "5 days ago"),
    ],
)
def test_format_timedelta_to_ago(td: timedelta, expected: str) -> None:
    """Test the format_timedelta_to_ago function."""
    assert utils.format_timedelta_to_ago(td) == expected


def test_get_clipboard_text() -> None:
    """Test reading from clipboard."""
    with patch("pyperclip.paste", return_value="hello world"):
        text = utils.get_clipboard_text(quiet=True)
        assert text == "hello world"


def test_get_clipboard_text_empty() -> None:
    """Test reading from an empty clipboard."""
    with patch("pyperclip.paste", return_value=""):
        text = utils.get_clipboard_text(quiet=True)
        assert text is None


def test_print_device_index() -> None:
    """Test the print_device_index function."""
    with patch("agent_cli.utils.console") as mock_console:
        utils.print_device_index(1, "mock_device")
        mock_console.print.assert_called_once()


def test_print_input_panel() -> None:
    """Test the print_input_panel function."""
    with patch("agent_cli.utils.console") as mock_console:
        utils.print_input_panel("hello")
        mock_console.print.assert_called_once()


def test_print_output_panel() -> None:
    """Test the print_output_panel function."""
    with patch("agent_cli.utils.console") as mock_console:
        utils.print_output_panel("hello")
        mock_console.print.assert_called_once()


def test_print_status_message() -> None:
    """Test the print_with_style function."""
    with patch("agent_cli.utils.console") as mock_console:
        utils.print_with_style("hello")
        mock_console.print.assert_called_once()


def test_print_error_message() -> None:
    """Test the print_error_message function."""
    with patch("agent_cli.utils.console") as mock_console:
        utils.print_error_message("hello", "world")
        mock_console.print.assert_called_once()


def test_interactive_stop_event() -> None:
    """Test the InteractiveStopEvent class."""
    stop_event = utils.InteractiveStopEvent()
    assert not stop_event.is_set()
    assert not stop_event.ctrl_c_pressed

    stop_event.set()
    assert stop_event.is_set()

    stop_event.clear()
    assert not stop_event.is_set()
    assert not stop_event.ctrl_c_pressed

    assert stop_event.increment_sigint_count() == 1
    assert stop_event.ctrl_c_pressed
    assert stop_event.increment_sigint_count() == 2

    stop_event.clear()
    assert not stop_event.ctrl_c_pressed
