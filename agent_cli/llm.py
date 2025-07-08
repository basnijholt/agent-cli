"""Client for interacting with LLMs."""

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

    from agent_cli.agents._config import LLMConfig, OllamaLLMConfig, OpenAILLMConfig


def build_agent(
    llm_config: LLMConfig,
    *,
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent."""
    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    provider_config: OpenAILLMConfig | OllamaLLMConfig
    if llm_config.provider == "openai":
        provider_config = llm_config.openai
        if not provider_config or not provider_config.api_key:
            msg = "OpenAI LLM config or API key is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(api_key=provider_config.api_key)
    else:  # local
        provider_config = llm_config.local
        if not provider_config:
            msg = "Local LLM config is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(base_url=f"{provider_config.host}/v1")

    llm_model = OpenAIModel(model_name=provider_config.model, provider=provider)
    return Agent(
        model=llm_model,
        system_prompt=system_prompt or (),
        instructions=instructions,
        tools=tools or [],
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
    llm_config: LLMConfig,
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
        llm_config=llm_config,
        system_prompt=system_prompt,
        instructions=agent_instructions,
        tools=tools,
    )

    start_time = time.monotonic()

    try:
        if llm_config.provider == "openai":
            provider_config = llm_config.openai
            if not provider_config:
                msg = "OpenAI LLM config is not set."
                raise ValueError(msg)  # noqa: TRY301
        else:
            provider_config = llm_config.local
            if not provider_config:
                msg = "Local LLM config is not set."
                raise ValueError(msg)  # noqa: TRY301
        model_name = provider_config.model

        async with live_timer(
            live or Live(console=console),
            f"🤖 Applying instruction with {model_name}",
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
        if llm_config.provider == "openai":
            msg = "Please check your OpenAI API key."
        else:
            host = llm_config.local.host if llm_config.local else "unknown"
            msg = f"Please check your Ollama server at [cyan]{host}[/cyan]"
        print_error_message(f"An unexpected LLM error occurred: {e}", msg)
        if exit_on_error:
            sys.exit(1)
        return None


async def process_and_update_clipboard(
    system_prompt: str,
    agent_instructions: str,
    *,
    llm_config: LLMConfig,
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
        llm_config=llm_config,
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=True,
    )
