"""Client for interacting with LLMs."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

import pyperclip
from rich.live import Live

from agent_cli import config
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
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent."""
    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIModel, OpenAIResponsesModelSettings  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    if config.SERVICE_PROVIDER == "openai":
        if not config.OPENAI_API_KEY:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(api_key=config.OPENAI_API_KEY)
    else:
        provider = OpenAIProvider(base_url=f"{config.OLLAMA_HOST}/v1")

    llm_model = OpenAIModel(model_name=model, provider=provider)
    return Agent(
        model=llm_model,
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
    live: Live | None = None,
    tools: list[Tool] | None = None,
    quiet: bool = False,
    clipboard: bool = False,
    show_output: bool = False,
    exit_on_error: bool = False,
) -> str | None:
    """Get a response from the LLM with optional clipboard and output handling."""
    agent = build_agent(
        model=model,
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
        if config.SERVICE_PROVIDER == "openai":
            msg = "Please check your OpenAI API key."
        else:
            msg = f"Please check your Ollama server at [cyan]{config.OLLAMA_HOST}[/cyan]"
        print_error_message(f"An unexpected LLM error occurred: {e}", msg)
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
        model=model,
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=True,
    )
