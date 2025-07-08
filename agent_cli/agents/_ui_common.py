"""Common UI display utilities for agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyperclip

from agent_cli.utils import (
    print_input_panel,
    print_output_panel,
    print_with_style,
)

if TYPE_CHECKING:
    from agent_cli.agents._config import GeneralConfig


def display_input_text(
    text: str,
    title: str = "📋 Original Text",
    general_cfg: GeneralConfig | None = None,
) -> None:
    """Display input text in a consistent format."""
    quiet = general_cfg.quiet if general_cfg else False
    if not quiet:
        print_input_panel(text, title=title)


def display_output_with_clipboard(
    output_text: str,
    original_text: str | None = None,
    elapsed: float | None = None,
    title: str = "✨ Output",
    success_message: str = "✅ Success! Result has been copied to your clipboard.",
    general_cfg: GeneralConfig | None = None,
) -> None:
    """Display output text and copy to clipboard with consistent formatting."""
    quiet = general_cfg.quiet if general_cfg else False

    # Copy to clipboard
    pyperclip.copy(output_text)

    if quiet:
        # Simple output for quiet mode
        if original_text and output_text.strip() == original_text.strip():
            print("✅ No changes needed.")
        else:
            print(output_text)
    else:
        # Rich output for normal mode
        subtitle = f"[dim]took {elapsed:.2f}s[/dim]" if elapsed else ""
        print_output_panel(output_text, title=title, subtitle=subtitle)
        print_with_style(success_message)


def display_no_input_warning(
    source: str = "clipboard",
    general_cfg: GeneralConfig | None = None,
) -> None:
    """Display warning when no input is available."""
    quiet = general_cfg.quiet if general_cfg else False
    if not quiet:
        print_with_style(f"⚠️ No input from {source}.", style="yellow")


def display_processing_status(
    message: str,
    general_cfg: GeneralConfig | None = None,
) -> None:
    """Display a processing status message."""
    quiet = general_cfg.quiet if general_cfg else False
    if not quiet:
        print_with_style(message, style="blue")
