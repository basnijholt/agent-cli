"""OpenAI LLM service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli import config
from agent_cli._tools import tools
from agent_cli.services.base import LLMService
from agent_cli.services.local.llm import build_agent

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class OpenAILLMService(LLMService):
    """OpenAI LLM service."""

    def __init__(self, openai_config: config.OpenAILLM, **kwargs) -> None:
        """Initialize the OpenAI LLM service."""
        super().__init__(**kwargs)
        self.openai_config = openai_config

    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        instructions: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Get a response from the LLM with optional clipboard and output handling."""
        agent = build_agent(
            provider_config=config.ProviderSelection(llm_provider="openai"),
            openai_config=self.openai_config,
            system_prompt=system_prompt,
            instructions=instructions,
            tools=tools(),
        )
        result = await agent.run(message)
        yield result.output
