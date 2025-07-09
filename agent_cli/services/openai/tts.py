"""OpenAI TTS service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.services.base import TTSService

if TYPE_CHECKING:
    from agent_cli import config


class OpenAITTSService(TTSService):
    """OpenAI TTS service."""

    def __init__(
        self,
        openai_tts_config: config.OpenAITTS,
        **kwargs,
    ) -> None:
        """Initialize the OpenAI TTS service."""
        super().__init__(**kwargs)
        self.openai_tts_config = openai_tts_config

    async def synthesise(self, text: str) -> bytes:  # noqa: ARG002
        """Synthesize speech from text using OpenAI TTS server."""
        # This is a placeholder implementation.
        # The actual implementation will be added in a future commit.
        return b"Hello from OpenAI TTS!"
