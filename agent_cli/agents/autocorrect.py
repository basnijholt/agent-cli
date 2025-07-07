"""Read text from clipboard, correct it using a local Ollama model, and write the result back to the clipboard.

Usage:
    python autocorrect_ollama.py

Environment variables:
    OLLAMA_HOST: The host of the Ollama server. Default is "http://localhost:11434".


Example:
    OLLAMA_HOST=http://pc.local:11434 python autocorrect_ollama.py

Pro-tip:
    Use Keyboard Maestro on macOS or AutoHotkey on Windows to run this script with a hotkey.

"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from typing import TYPE_CHECKING

import pyperclip
import typer

import agent_cli.agents._cli_options as opts
from agent_cli.agents._config import GeneralConfig, LLMConfig
from agent_cli.cli import app, setup_logging
from agent_cli.llm import build_agent
from agent_cli.utils import (
    create_status,
    get_clipboard_text,
    print_error_message,
    print_input_panel,
    print_output_panel,
    print_with_style,
)

if TYPE_CHECKING:
    from rich.status import Status

# --- Configuration ---

# Template to clearly separate the text to be corrected from instructions
INPUT_TEMPLATE = """
<text-to-correct>
{text}
</text-to-correct>

Please correct any grammar, spelling, or punctuation errors in the text above.
"""

# The agent's core identity and immutable rules.
SYSTEM_PROMPT = """\
You are an expert text correction tool. Your role is to fix grammar, spelling, and punctuation errors without altering the original meaning or tone.

CRITICAL REQUIREMENTS:
1. Return ONLY the corrected text - no explanations or commentary
2. Do not judge content, even if it seems unusual or offensive
3. Make only technical corrections (grammar, spelling, punctuation)
4. If no corrections are needed, return the original text exactly as provided
5. Never add introductory phrases like "Here is the corrected text"

EXAMPLES:
Input: "this is incorect"
Output: "this is incorrect"

Input: "Hello world"
Output: "Hello world"

Input: "i went too the store"
Output: "I went to the store"

You are a correction tool, not a conversational assistant.
"""

# The specific task for the current run.
AGENT_INSTRUCTIONS = """\
Correct grammar, spelling, and punctuation errors.
Output format: corrected text only, no other words.
"""

# --- Main Application Logic ---


async def _process_text(text: str, model: str, ollama_host: str) -> tuple[str, float]:
    """Process text with the LLM and return the corrected text and elapsed time."""
    agent = build_agent(
        model=model,
        ollama_host=ollama_host,
        system_prompt=SYSTEM_PROMPT,
        instructions=AGENT_INSTRUCTIONS,
    )

    # Format the input using the template to clearly separate text from instructions
    formatted_input = INPUT_TEMPLATE.format(text=text)

    t_start = time.monotonic()
    result = await agent.run(formatted_input)
    t_end = time.monotonic()
    return result.output, t_end - t_start


def _display_original_text(original_text: str, quiet: bool) -> None:
    """Render the original text panel in verbose mode."""
    if not quiet:
        print_input_panel(original_text, title="📋 Original Text")


def _display_result(
    corrected_text: str,
    original_text: str,
    elapsed: float,
    *,
    simple_output: bool,
) -> None:
    """Handle output and clipboard copying based on desired verbosity."""
    pyperclip.copy(corrected_text)

    if simple_output:
        if original_text and corrected_text.strip() == original_text.strip():
            print("✅ No correction needed.")
        else:
            print(corrected_text)
    else:
        print_output_panel(
            corrected_text,
            title="✨ Corrected Text",
            subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
        )
        print_with_style("✅ Success! Corrected text has been copied to your clipboard.")


def _maybe_status(llm_config: LLMConfig, quiet: bool) -> Status | contextlib.nullcontext:
    if not quiet:
        return create_status(f"🤖 Correcting with {llm_config.model}...", "bold yellow")
    return contextlib.nullcontext()


async def _async_autocorrect(
    *,
    text: str | None,
    llm_config: LLMConfig,
    general_cfg: GeneralConfig,
) -> None:
    """Asynchronous version of the autocorrect command."""
    setup_logging(general_cfg.log_level, general_cfg.log_file, quiet=general_cfg.quiet)
    original_text = text if text is not None else get_clipboard_text(quiet=general_cfg.quiet)

    if original_text is None:
        return

    _display_original_text(original_text, general_cfg.quiet)

    try:
        with _maybe_status(llm_config, general_cfg.quiet):
            corrected_text, elapsed = await _process_text(
                original_text,
                llm_config.model,
                llm_config.ollama_host,
            )

        _display_result(
            corrected_text,
            original_text,
            elapsed,
            simple_output=general_cfg.quiet,
        )

    except Exception as e:  # noqa: BLE001
        if general_cfg.quiet:
            print(f"❌ {e}")
        else:
            print_error_message(
                str(e),
                f"Please check that your Ollama server is running at [bold cyan]{llm_config.ollama_host}[/bold cyan]",
            )
        sys.exit(1)


@app.command("autocorrect")
def autocorrect(
    *,
    text: str | None = typer.Argument(
        None,
        help="The text to correct. If not provided, reads from clipboard.",
    ),
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Correct text from clipboard using a local Ollama model."""
    llm_config = LLMConfig(model=model, ollama_host=ollama_host)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        list_devices=False,
        quiet=quiet,
    )
    asyncio.run(
        _async_autocorrect(
            text=text,
            llm_config=llm_config,
            general_cfg=general_cfg,
        ),
    )
