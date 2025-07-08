"""Read text from clipboard, correct it using a local Ollama model, and write the result back to the clipboard.

Usage:
    agent-cli autocorrect [TEXT]

Environment variables:
    OLLAMA_HOST: The host of the Ollama server. Default is "http://localhost:11434".

Example:
    OLLAMA_HOST=http://pc.local:11434 agent-cli autocorrect

Pro-tip:
    Use Keyboard Maestro on macOS or AutoHotkey on Windows to run this script with a hotkey.

"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import TYPE_CHECKING

import typer

import agent_cli.agents._cli_options as opts
from agent_cli.agents._command_setup import CommandConfig, setup_command
from agent_cli.agents._llm_common import handle_llm_error, process_with_llm
from agent_cli.agents._ui_common import display_input_text, display_output_with_clipboard
from agent_cli.cli import app
from agent_cli.utils import create_status, get_clipboard_text

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


def _maybe_status(model: str, quiet: bool) -> Status | contextlib.nullcontext:
    """Create status context if not in quiet mode."""
    if not quiet:
        return create_status(f"🤖 Correcting with {model}...", "bold yellow")
    return contextlib.nullcontext()


async def _async_autocorrect(text: str | None, config: CommandConfig) -> None:
    """Asynchronous autocorrect implementation."""
    # Ensure we have LLM config (should always be present for autocorrect)
    if config.llm_config is None:
        msg = "LLM configuration is required for autocorrect"
        raise ValueError(msg)

    # Get text from argument or clipboard
    original_text = text if text is not None else get_clipboard_text(quiet=config.general_cfg.quiet)
    if original_text is None:
        return

    # Display input
    display_input_text(original_text, title="📋 Original Text", general_cfg=config.general_cfg)

    # Process with LLM
    with _maybe_status(config.llm_config.model, config.general_cfg.quiet):
        result = await process_with_llm(
            original_text,
            config.llm_config,
            SYSTEM_PROMPT,
            AGENT_INSTRUCTIONS,
            INPUT_TEMPLATE,
        )

    # Handle result
    if result["success"]:
        display_output_with_clipboard(
            result["output"],
            original_text=original_text,
            elapsed=result["elapsed"],
            title="✨ Corrected Text",
            success_message="✅ Success! Corrected text has been copied to your clipboard.",
            general_cfg=config.general_cfg,
        )
    else:
        if result["error"] is not None:
            handle_llm_error(result["error"], config.llm_config, config.general_cfg.quiet)
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
    llm_provider: str = opts.LLM_PROVIDER,
    openai_api_key: str = opts.OPENAI_API_KEY,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Correct text from clipboard using a local Ollama model."""
    # Common setup
    config = setup_command(
        process_name="autocorrect",
        command_description="autocorrect",
        stop=False,  # autocorrect doesn't support background process
        status=False,
        toggle=False,
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        model=model,
        ollama_host=ollama_host,
        llm_provider=llm_provider,
        openai_api_key=openai_api_key,
    )

    if config is None:  # Should not happen for autocorrect
        return

    # Run async autocorrect
    asyncio.run(_async_autocorrect(text, config))
