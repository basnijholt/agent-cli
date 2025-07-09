"""Read text from clipboard, correct it using a local or remote LLM, and write the result back to the clipboard."""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from typing import TYPE_CHECKING

import pyperclip
import typer

from agent_cli import config, opts
from agent_cli.cli import app
from agent_cli.core.utils import (
    create_status,
    get_clipboard_text,
    print_error_message,
    print_input_panel,
    print_output_panel,
    print_with_style,
    setup_logging,
)
from agent_cli.services.llm import build_agent

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


async def _process_text(
    text: str,
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
) -> tuple[str, float]:
    """Process text with the LLM and return the corrected text and elapsed time."""
    agent = build_agent(
        provider_config=provider_cfg,
        ollama_config=ollama_cfg,
        openai_config=openai_llm_cfg,
        system_prompt=SYSTEM_PROMPT,
        instructions=AGENT_INSTRUCTIONS,
    )

    # Format the input using the template to clearly separate text from instructions
    formatted_input = INPUT_TEMPLATE.format(text=text)

    start_time = time.monotonic()
    result = await agent.run(formatted_input)
    elapsed = time.monotonic() - start_time
    return result.output, elapsed


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


def _maybe_status(
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    quiet: bool,
) -> Status | contextlib.nullcontext:
    if not quiet:
        model_name = (
            ollama_cfg.ollama_model
            if provider_cfg.llm_provider == "local"
            else openai_llm_cfg.openai_llm_model
        )
        return create_status(f"🤖 Correcting with {model_name}...", "bold yellow")
    return contextlib.nullcontext()


async def _async_autocorrect(
    *,
    text: str | None,
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    general_cfg: config.General,
) -> None:
    """Asynchronous version of the autocorrect command."""
    setup_logging(general_cfg.log_level, general_cfg.log_file, quiet=general_cfg.quiet)
    original_text = text if text is not None else get_clipboard_text(quiet=general_cfg.quiet)

    if original_text is None:
        return

    _display_original_text(original_text, general_cfg.quiet)

    try:
        with _maybe_status(provider_cfg, ollama_cfg, openai_llm_cfg, general_cfg.quiet):
            corrected_text, elapsed = await _process_text(
                original_text,
                provider_cfg,
                ollama_cfg,
                openai_llm_cfg,
            )

        _display_result(corrected_text, original_text, elapsed, simple_output=general_cfg.quiet)

    except Exception as e:  # noqa: BLE001
        if general_cfg.quiet:
            print(f"❌ {e}")
        else:
            if provider_cfg.llm_provider == "local":
                error_details = f"Please check that your Ollama server is running at [bold cyan]{ollama_cfg.ollama_host}[/bold cyan]"
            else:
                error_details = "Please check your OpenAI API key and network connection."
            print_error_message(str(e), error_details)
        sys.exit(1)


@app.command("autocorrect")
def autocorrect(
    *,
    text: str | None = typer.Argument(
        None,
        help="The text to correct. If not provided, reads from clipboard.",
        rich_help_panel="General Options",
    ),
    # --- Provider Selection ---
    llm_provider: str = opts.LLM_PROVIDER,
    # --- LLM Configuration ---
    # Ollama (local service)
    ollama_model: str = opts.OLLAMA_MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    # OpenAI
    openai_llm_model: str = opts.OPENAI_LLM_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    # --- General Options ---
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Correct text from clipboard using a local or remote LLM."""
    provider_cfg = config.ProviderSelection(
        llm_provider=llm_provider,
        asr_provider="local",  # Not used, but required by model
        tts_provider="local",  # Not used, but required by model
    )
    ollama_cfg = config.Ollama(ollama_model=ollama_model, ollama_host=ollama_host)
    openai_llm_cfg = config.OpenAILLM(
        openai_llm_model=openai_llm_model,
        openai_api_key=openai_api_key,
    )
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        clipboard=True,
    )
    asyncio.run(
        _async_autocorrect(
            text=text,
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            general_cfg=general_cfg,
        ),
    )
