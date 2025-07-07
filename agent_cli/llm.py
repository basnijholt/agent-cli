"""Client for interacting with Ollama."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pyperclip
from rich.live import Live

from agent_cli.utils import (
    console,
    live_timer,
    print_error_message,
    print_output_panel,
)

if TYPE_CHECKING:
    import logging

    from pydantic_ai import Agent
    from pydantic_ai.tools import Tool


def build_agent(
    model: str,
    ollama_host: str,
    *,
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent configured for local Ollama."""
    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModelSettings  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    ollama_provider = OpenAIProvider(base_url=f"{ollama_host}/v1")
    ollama_model = OpenAIModel(model_name=model, provider=ollama_provider)
    return Agent(
        model=ollama_model,
        system_prompt=system_prompt or (),
        instructions=instructions,
        tools=tools or [],
        model_settings=OpenAIResponsesModelSettings(extra_body={"think": False}),
    )


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
    model: str,
    ollama_host: str,
    logger: logging.Logger,
    live: Live | None = None,
    tools: list[Tool] | None = None,
    quiet: bool = False,
    clipboard: bool = False,
    show_output: bool = False,
    exit_on_error: bool = False,
) -> str | None:
    """Get a response from the LLM with optional clipboard and output handling.

    Args:
        system_prompt: System prompt for the LLM
        agent_instructions: Agent instructions
        user_input: Input text for the LLM
        model: Model name
        ollama_host: Ollama server host
        logger: Logger instance
        live: Existing Live instance
        tools: Optional list of tools for the agent
        quiet: If True, suppress timer display
        clipboard: If True, copy result to clipboard
        show_output: If True, display result in rich panel
        exit_on_error: If True, exit on error instead of returning None

    Returns:
        LLM response text or None if error and exit_on_error=False

    """
    agent = build_agent(
        model=model,
        ollama_host=ollama_host,
        system_prompt=system_prompt,
        instructions=agent_instructions,
        tools=tools,
    )

    start_time = time.monotonic()

    try:
        async with live_timer(
            live or Live(console=console),
            f"🤖 Applying instruction with {model}",
            style="bold yellow",
            quiet=quiet,
        ):
            result = await agent.run(user_input)

        elapsed = time.monotonic() - start_time
        result_text = result.output

        # Handle clipboard copying
        if clipboard:
            pyperclip.copy(result_text)
            logger.info("Copied result to clipboard.")

        # Handle output display
        if show_output and not quiet:
            print_output_panel(
                result_text,
                title="✨ Result (Copied to Clipboard)" if clipboard else "✨ Result",
                subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
            )
        elif quiet and clipboard:
            # Quiet mode: print result to stdout for Keyboard Maestro to capture
            print(result_text)

        return result_text

    except Exception as e:
        logger.exception("An error occurred during LLM processing.")
        print_error_message(
            f"An unexpected LLM error occurred: {e}",
            f"Please check your Ollama server at [cyan]{ollama_host}[/cyan]",
        )
        if exit_on_error:
            sys.exit(1)
        return None


async def process_and_update_clipboard(
    system_prompt: str,
    agent_instructions: str,
    *,
    model: str,
    ollama_host: str,
    logger: logging.Logger,
    original_text: str,
    instruction: str,
    clipboard: bool,
    quiet: bool,
    live: Live,
) -> None:
    """Processes the text with the LLM, updates the clipboard, and displays the result.

    In quiet mode, only the result is printed to stdout.
    """
    # Format input using the template
    user_input = INPUT_TEMPLATE.format(
        original_text=original_text,
        instruction=instruction,
    )

    await get_llm_response(
        system_prompt=system_prompt,
        agent_instructions=agent_instructions,
        user_input=user_input,
        model=model,
        ollama_host=ollama_host,
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=True,
    )
