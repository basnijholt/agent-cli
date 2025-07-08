"""Common LLM processing utilities for agents."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypedDict

from agent_cli.llm import build_agent
from agent_cli.utils import print_error_message

if TYPE_CHECKING:
    from agent_cli.agents._config import LLMConfig


class LLMResult(TypedDict):
    """Result from LLM processing."""

    output: str
    elapsed: float
    success: bool
    error: str | None


async def process_with_llm(
    input_text: str,
    llm_config: LLMConfig,
    system_prompt: str,
    agent_instructions: str,
    input_template: str | None = None,
) -> LLMResult:
    """Process text with LLM and return result with timing.

    Args:
        input_text: The text to process
        llm_config: LLM configuration
        system_prompt: System prompt for the agent
        agent_instructions: Specific instructions for the agent
        input_template: Optional template to format input text

    Returns:
        LLMResult with output, elapsed time, and status

    """
    try:
        agent = build_agent(
            model=llm_config.model,
            ollama_host=llm_config.ollama_host,
            system_prompt=system_prompt,
            instructions=agent_instructions,
        )

        # Format input if template provided
        formatted_input = input_template.format(text=input_text) if input_template else input_text

        t_start = time.monotonic()
        result = await agent.run(formatted_input)
        t_end = time.monotonic()

        return {
            "output": result.output,
            "elapsed": t_end - t_start,
            "success": True,
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "output": "",
            "elapsed": 0.0,
            "success": False,
            "error": str(e),
        }


def handle_llm_error(
    error: str,
    llm_config: LLMConfig,
    quiet: bool,
) -> None:
    """Handle LLM processing errors consistently."""
    if quiet:
        print(f"❌ {error}")
    else:
        print_error_message(
            error,
            f"Please check that your Ollama server is running at [bold cyan]{llm_config.ollama_host}[/bold cyan]",
        )
