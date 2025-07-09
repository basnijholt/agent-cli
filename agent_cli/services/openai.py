"""Module for interacting with OpenAI services."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from agent_cli.services.base import ASRService, LLMService, TTSService

if TYPE_CHECKING:
    import logging

    from openai import AsyncOpenAI

    from agent_cli import config


def _get_openai_client(api_key: str) -> AsyncOpenAI:
    """Get an OpenAI client instance."""
    from openai import AsyncOpenAI  # noqa: PLC0415

    if not api_key:
        msg = "OpenAI API key is not set."
        raise ValueError(msg)
    return AsyncOpenAI(api_key=api_key)


class OpenAITranscriptionService(ASRService):
    """Transcription service using OpenAI's Whisper API."""

    def __init__(
        self,
        openai_asr_config: config.OpenAIASR,
        openai_llm_config: config.OpenAILLM,
        logger: logging.Logger,
    ) -> None:
        """Initialize the OpenAITranscriptionService."""
        self.openai_asr_config = openai_asr_config
        self.openai_llm_config = openai_llm_config
        self.logger = logger
        if not self.openai_llm_config.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        self.client = _get_openai_client(api_key=self.openai_llm_config.openai_api_key)

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using OpenAI's Whisper API."""
        self.logger.info("Transcribing audio with OpenAI Whisper...")
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"
        response = await self.client.audio.transcriptions.create(
            model=self.openai_asr_config.openai_asr_model,
            file=audio_file,
        )
        return response.text


class OpenAILLMService(LLMService):
    """LLM service using OpenAI's API."""

    def __init__(
        self,
        openai_llm_config: config.OpenAILLM,
        logger: logging.Logger,
    ) -> None:
        """Initialize the OpenAILLMService."""
        from pydantic_ai.models.openai import OpenAIModel  # noqa: PLC0415
        from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

        self.openai_llm_config = openai_llm_config
        self.logger = logger
        if not self.openai_llm_config.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        provider = OpenAIProvider(api_key=self.openai_llm_config.openai_api_key)
        self.model = OpenAIModel(
            model_name=self.openai_llm_config.openai_llm_model,
            provider=provider,
        )

    async def get_response(
        self,
        *,
        system_prompt: str,
        agent_instructions: str,
        user_input: str,
        tools: list | None = None,
    ) -> str | None:
        """Get a response from the language model."""
        from pydantic_ai import Agent  # noqa: PLC0415

        agent = Agent(
            model=self.model,
            system_prompt=system_prompt or (),
            instructions=agent_instructions,
            tools=tools or [],
        )
        result = await agent.run(user_input)
        return result.output


class OpenAITTSService(TTSService):
    """TTS service using OpenAI's API."""

    def __init__(
        self,
        openai_tts_config: config.OpenAITTS,
        openai_llm_config: config.OpenAILLM,
        logger: logging.Logger,
    ) -> None:
        """Initialize the OpenAITTSService."""
        self.openai_tts_config = openai_tts_config
        self.openai_llm_config = openai_llm_config
        self.logger = logger
        if not self.openai_llm_config.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)
        self.client = _get_openai_client(api_key=self.openai_llm_config.openai_api_key)

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech using OpenAI's TTS API."""
        self.logger.info("Synthesizing speech with OpenAI TTS...")
        response = await self.client.audio.speech.create(
            model=self.openai_tts_config.openai_tts_model,
            voice=self.openai_tts_config.openai_tts_voice,
            input=text,
            response_format="wav",
        )
        return response.content
