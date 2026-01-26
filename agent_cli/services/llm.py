"""Client for interacting with LLMs."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

from rich.live import Live

from agent_cli.core.utils import console, live_timer, print_error_message, print_output_panel

if TYPE_CHECKING:
    import logging

    from pydantic_ai import Agent
    from pydantic_ai.models.gemini import GeminiModel
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.tools import Tool

    from agent_cli import config


def _openai_llm_model(openai_cfg: config.OpenAILLM) -> OpenAIModel:
    from pydantic_ai.models.openai import OpenAIModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    # For custom base URLs (like llama-server), API key might not be required
    if openai_cfg.openai_base_url:
        # Custom endpoint - API key is optional
        provider = OpenAIProvider(
            api_key=openai_cfg.openai_api_key or "dummy",
            base_url=openai_cfg.openai_base_url,
        )
    else:
        # Standard OpenAI - API key is required
        if not openai_cfg.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(api_key=openai_cfg.openai_api_key)

    model_name = openai_cfg.llm_openai_model
    return OpenAIModel(model_name=model_name, provider=provider)


def _ollama_llm_model(ollama_cfg: config.Ollama) -> OpenAIModel:
    from pydantic_ai.models.openai import OpenAIModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    provider = OpenAIProvider(base_url=f"{ollama_cfg.llm_ollama_host}/v1")
    model_name = ollama_cfg.llm_ollama_model
    return OpenAIModel(model_name=model_name, provider=provider)


def _gemini_llm_model(gemini_cfg: config.GeminiLLM) -> GeminiModel:
    from pydantic_ai.models.gemini import GeminiModel  # noqa: PLC0415
    from pydantic_ai.providers.google_gla import GoogleGLAProvider  # noqa: PLC0415

    if not gemini_cfg.gemini_api_key:
        msg = "Gemini API key is not set."
        raise ValueError(msg)
    provider = GoogleGLAProvider(api_key=gemini_cfg.gemini_api_key)
    model_name = gemini_cfg.llm_gemini_model
    return GeminiModel(model_name=model_name, provider=provider)


def create_llm_agent(
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_cfg: config.OpenAILLM,
    gemini_cfg: config.GeminiLLM,
    *,
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent."""
    from pydantic_ai import Agent  # noqa: PLC0415

    if provider_cfg.llm_provider == "openai":
        llm_model = _openai_llm_model(openai_cfg)
    elif provider_cfg.llm_provider == "ollama":
        llm_model = _ollama_llm_model(ollama_cfg)
    elif provider_cfg.llm_provider == "gemini":
        llm_model = _gemini_llm_model(gemini_cfg)

    return Agent(
        model=llm_model,
        system_prompt=system_prompt or (),
        instructions=instructions,
        tools=tools or [],
    )


# --- LLM (Editing) Logic ---

INPUT_TEMPLATE = """
{context_block}<original-text>
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
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_cfg: config.OpenAILLM,
    gemini_cfg: config.GeminiLLM,
    logger: logging.Logger,
    live: Live | None = None,
    tools: list[Tool] | None = None,
    quiet: bool = False,
    clipboard: bool = False,
    show_output: bool = False,
    exit_on_error: bool = False,
) -> str | None:
    """Get a response from the LLM with optional clipboard and output handling."""
    agent = create_llm_agent(
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_cfg,
        gemini_cfg=gemini_cfg,
        system_prompt=system_prompt,
        instructions=agent_instructions,
        tools=tools,
    )

    start_time = time.monotonic()

    try:
        if provider_cfg.llm_provider == "ollama":
            model_name = ollama_cfg.llm_ollama_model
        elif provider_cfg.llm_provider == "openai":
            model_name = openai_cfg.llm_openai_model
        elif provider_cfg.llm_provider == "gemini":
            model_name = gemini_cfg.llm_gemini_model

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
            import pyperclip  # noqa: PLC0415

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
        if provider_cfg.llm_provider == "openai":
            msg = "Please check your OpenAI API key."
        elif provider_cfg.llm_provider == "gemini":
            msg = "Please check your Gemini API key."
        elif provider_cfg.llm_provider == "ollama":
            msg = f"Please check your Ollama server at [cyan]{ollama_cfg.llm_ollama_host}[/cyan]"
        print_error_message(f"An unexpected LLM error occurred: {e}", msg)
        if exit_on_error:
            sys.exit(1)
        return None


async def process_and_update_clipboard(
    system_prompt: str,
    agent_instructions: str,
    *,
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_cfg: config.OpenAILLM,
    gemini_cfg: config.GeminiLLM,
    logger: logging.Logger,
    original_text: str,
    instruction: str,
    clipboard: bool,
    quiet: bool,
    live: Live | None,
    context: str | None = None,
) -> str | None:
    """Processes the text with the LLM, updates the clipboard, and displays the result."""
    context_block = ""
    if context:
        context_block = f"<context>\n{context}\n</context>\n\n"
    user_input = INPUT_TEMPLATE.format(
        context_block=context_block,
        original_text=original_text,
        instruction=instruction,
    )

    return await get_llm_response(
        system_prompt=system_prompt,
        agent_instructions=agent_instructions,
        user_input=user_input,
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_cfg,
        gemini_cfg=gemini_cfg,
        logger=logger,
        quiet=quiet,
        clipboard=clipboard,
        live=live,
        show_output=True,
        exit_on_error=False,  # Don't exit the server on LLM errors
    )
