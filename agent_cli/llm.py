"""Client for interacting with LLMs."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pyperclip
from rich.live import Live

from agent_cli.core.utils import console, live_timer, print_error_message, print_output_panel
from agent_cli.services.factory import get_llm_service

if TYPE_CHECKING:
    import logging

    from pydantic_ai import Agent
    from pydantic_ai.tools import Tool

    from agent_cli.agents import config




# --- LLM (Editing) Logic ---

INPUT_TEMPLATE = """
<original-text>
{original_text}
</original-text>

<instruction>
{instruction}
</instruction>
"""


async def get_llm_response(
    *,
    system_prompt: str,
    agent_instructions: str,
    user_input: str,
    provider_config: config.ProviderSelection,
    ollama_config: config.Ollama,
    openai_config: config.OpenAILLM,
    logger: logging.Logger,
    live: Live | None = None,
    tools: list[Tool] | None = None,
    quiet: bool = False,
    clipboard: bool = False,
    show_output: bool = False,
    exit_on_error: bool = False,
) -> str | None:
    """Get a response from the LLM with optional clipboard and output handling."""
    llm_service = get_llm_service(
        provider_config, ollama_config, openai_config, logger
    )

    start_time = time.monotonic()

    try:
        model_name = (
            ollama_config.ollama_model
            if provider_config.llm_provider == "local"
            else openai_config.openai_llm_model
        )

        async with live_timer(
            live or Live(console=console),
            f"🤖 Applying instruction with {model_name}",
            style="bold yellow",
            quiet=quiet,
        ):
            result_text = await llm_service.get_response(
                system_prompt=system_prompt,
                agent_instructions=agent_instructions,
                user_input=user_input,
                tools=tools,
            )

        elapsed = time.monotonic() - start_time

        if not result_text:
            return None

        if clipboard:
            pyperclip.copy(result_text)
            logger.info("Copied result to clipboard.")

        if show_output and not quiet:
            print_output_panel(
                result_text,
                title="✨ Result (Copied to Clipboard)" if clipboard else "✨ Result",
                subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
            )
        elif quiet and clipboard:
            print(result_text)

        return result_text

    except Exception as e:
        logger.exception("An error occurred during LLM processing.")
        if provider_config.llm_provider == "openai":
            msg = "Please check your OpenAI API key."
        else:
            msg = f"Please check your Ollama server at [cyan]{ollama_config.ollama_host}[/cyan]"
        print_error_message(f"An unexpected LLM error occurred: {e}", msg)
        if exit_on_error:
            sys.exit(1)
        return None


async def process_and_update_clipboard(
    system_prompt: str,
    agent_instructions: str,
    *,
    provider_config: config.ProviderSelection,
    ollama_config: config.Ollama,
    openai_config: config.OpenAILLM,
    logger: logging.Logger,
    original_text: str,
    instruction: str,
    clipboard: bool,
    quiet: bool,
    live: Live,
) -> None:
    """Processes the text with the LLM, updates the clipboard, and displays the result."""
    user_input = INPUT_TEMPLATE.format(
        original_text=original_text,
        instruction=instruction,
    )

    await get_llm_response(
        system_prompt=system_prompt,
        agent_instructions=agent_instructions,
        user_input=user_input,
        provider_config=provider_config,
        ollama_config=ollama_config,
        openai_config=openai_config,
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=True,
    )
