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
    *,
    llm_provider: str = "ollama",
    ollama_host: str | None = None,
    api_key: str | None = None,
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModelSettings
    from pydantic_ai.providers.openai import OpenAIProvider

    if llm_provider == "ollama":
        if not ollama_host:
            raise ValueError("ollama_host must be provided for ollama provider")
        provider = OpenAIProvider(base_url=f"{ollama_host}/v1")
    elif llm_provider == "openai":
        provider = OpenAIProvider(api_key=api_key)
    else:
        raise ValueError(f"Unknown llm_provider: {llm_provider}")

    model_instance = OpenAIModel(model_name=model, provider=provider)
    return Agent(
        model=model_instance,
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
    logger: logging.Logger,
    llm_provider: str = "ollama",
    ollama_host: str | None = None,
    openai_api_key: str | None = None,
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
        logger: Logger instance
        llm_provider: The LLM provider to use ("ollama" or "openai")
        ollama_host: Ollama server host
        openai_api_key: OpenAI API key
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
        llm_provider=llm_provider,
        ollama_host=ollama_host,
        api_key=openai_api_key,
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
        provider_name = "Ollama" if llm_provider == "ollama" else "OpenAI"
        error_msg = f"Please check your {provider_name} server at [cyan]{ollama_host}[/cyan]"
        if llm_provider == "openai":
            error_msg = "Please check your OpenAI API key and connection."
        print_error_message(
            f"An unexpected LLM error occurred: {e}",
            error_msg,
        )
        if exit_on_error:
            sys.exit(1)
        return None


async def process_and_update_clipboard(
    system_prompt: str,
    agent_instructions: str,
    *,
    model: str,
    logger: logging.Logger,
    original_text: str,
    instruction: str,
    clipboard: bool,
    quiet: bool,
    live: Live,
    llm_provider: str = "ollama",
    ollama_host: str | None = None,
    openai_api_key: str | None = None,
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
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=True,
        llm_provider=llm_provider,
        ollama_host=ollama_host,
        openai_api_key=openai_api_key,
    )
