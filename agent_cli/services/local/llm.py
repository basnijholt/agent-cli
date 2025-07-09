"""Local LLM service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent_cli import config
from agent_cli._tools import tools
from agent_cli.services.base import LLMService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from pydantic_ai.tools import Tool


def build_agent(
    provider_config: config.ProviderSelection,
    ollama_config: config.Ollama | None = None,
    openai_config: config.OpenAILLM | None = None,
    *,
    system_prompt: str | None = None,
    instructions: str | None = None,
    tools: list[Tool] | None = None,
) -> Agent:
    """Construct and return a PydanticAI agent."""
    if provider_config.llm_provider == "openai":
        assert openai_config is not None
        if not openai_config.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(api_key=openai_config.openai_api_key)
        model_name = openai_config.openai_llm_model
    else:
        assert ollama_config is not None
        provider = OpenAIProvider(base_url=f"{ollama_config.ollama_host}/v1")
        model_name = ollama_config.ollama_model

    llm_model = OpenAIModel(model_name=model_name, provider=provider)
    return Agent(
        model=llm_model,
        system_prompt=system_prompt or (),
        instructions=instructions,
        tools=tools or [],
    )


class OllamaLLMService(LLMService):
    """Ollama LLM service."""

    def __init__(self, ollama_config: config.Ollama, **kwargs) -> None:
        """Initialize the Ollama LLM service."""
        super().__init__(**kwargs)
        self.ollama_config = ollama_config

    async def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        instructions: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Get a response from the LLM with optional clipboard and output handling."""
        agent = build_agent(
            provider_config=config.ProviderSelection(
                llm_provider="local",
                asr_provider="local",
                tts_provider="local",
            ),
            ollama_config=self.ollama_config,
            system_prompt=system_prompt,
            instructions=instructions,
            tools=tools(),
        )
        result = await agent.run(message)
        yield result.output
