"""Module for interacting with local services like Wyoming and Ollama."""

from __future__ import annotations

import asyncio
import io
import wave
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.tts import Synthesize, SynthesizeVoice
from wyoming.wake import Detect, Detection, NotDetected

from agent_cli import constants
from agent_cli.core.audio import read_from_queue
from agent_cli.services.base import ASRService, LLMService, TTSService, WakeWordService

if TYPE_CHECKING:
    import logging
    from collections.abc import AsyncGenerator, Coroutine

    from rich.live import Live

    from agent_cli import config


@asynccontextmanager
async def wyoming_client_context(
    host: str,
    port: int,
    service_name: str,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> AsyncGenerator[AsyncClient, None]:
    """Connect to a Wyoming server."""
    if not quiet:
        logger.info("Connecting to %s server at %s:%s", service_name, host, port)
    try:
        async with AsyncClient(host, port) as client:
            yield client
    except ConnectionRefusedError:
        logger.exception(
            "Connection refused to %s server at %s:%s",
            service_name,
            host,
            port,
        )
        raise


async def manage_send_receive_tasks(
    send_task: Coroutine[Any, Any, Any],
    recv_task: Coroutine[Any, Any, Any],
    return_when: str = asyncio.ALL_COMPLETED,
) -> tuple[asyncio.Task, asyncio.Task]:
    """Manage send and receive tasks for a Wyoming client."""
    send: asyncio.Task = asyncio.create_task(send_task)
    recv: asyncio.Task = asyncio.create_task(recv_task)
    done, pending = await asyncio.wait({send, recv}, return_when=return_when)
    for task in pending:
        task.cancel()
    return send, recv


class WyomingTranscriptionService(ASRService):
    """Transcription service using a Wyoming ASR server."""

    def __init__(
        self,
        wyoming_asr_config: config.WyomingASR,
        logger: logging.Logger,
        *,
        quiet: bool = False,
    ) -> None:
        """Initialize the WyomingTranscriptionService."""
        self.wyoming_asr_config = wyoming_asr_config
        self.logger = logger
        self.quiet = quiet

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using a Wyoming ASR server."""
        async with wyoming_client_context(
            self.wyoming_asr_config.wyoming_asr_ip,
            self.wyoming_asr_config.wyoming_asr_port,
            "ASR",
            self.logger,
            quiet=self.quiet,
        ) as client:
            await client.write_event(Transcribe().event())
            await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())

            chunk_size = constants.PYAUDIO_CHUNK_SIZE * 2
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i : i + chunk_size]
                await client.write_event(
                    AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event(),
                )
            await client.write_event(AudioStop().event())
            return await self._receive_transcript(client)

    async def _receive_transcript(self, client: AsyncClient) -> str:
        """Receive transcription events and return the final transcript."""
        transcript_text = ""
        while True:
            event = await client.read_event()
            if event is None:
                self.logger.warning("Connection to ASR server lost.")
                break
            if Transcript.is_type(event.type):
                transcript = Transcript.from_event(event)
                transcript_text = transcript.text
                break
        return transcript_text


class OllamaLLMService(LLMService):
    """LLM service using an Ollama server."""

    def __init__(
        self,
        ollama_config: config.Ollama,
        logger: logging.Logger,
    ) -> None:
        """Initialize the OllamaLLMService."""
        self.ollama_config = ollama_config
        self.logger = logger
        provider = OpenAIProvider(base_url=f"{self.ollama_config.ollama_host}/v1")
        self.model = OpenAIModel(
            model_name=self.ollama_config.ollama_model,
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
        agent = Agent(
            model=self.model,
            system_prompt=system_prompt or (),
            instructions=agent_instructions,
            tools=tools or [],
        )
        result = await agent.run(user_input)
        return result.output


class WyomingTTSService(TTSService):
    """TTS service using a Wyoming TTS server."""

    def __init__(
        self,
        wyoming_tts_config: config.WyomingTTS,
        logger: logging.Logger,
        *,
        quiet: bool = False,
    ) -> None:
        """Initialize the WyomingTTSService."""
        self.wyoming_tts_config = wyoming_tts_config
        self.logger = logger
        self.quiet = quiet

    async def synthesize(self, text: str) -> bytes | None:
        """Synthesize speech using a Wyoming TTS server."""
        async with wyoming_client_context(
            self.wyoming_tts_config.wyoming_tts_ip,
            self.wyoming_tts_config.wyoming_tts_port,
            "TTS",
            self.logger,
            quiet=self.quiet,
        ) as client:
            synthesize_event = self._create_synthesis_request(text)
            _send_task, recv_task = await manage_send_receive_tasks(
                client.write_event(synthesize_event.event()),
                self._process_audio_events(client),
            )
            audio_data, sample_rate, sample_width, channels = recv_task.result()
            if sample_rate and sample_width and channels and audio_data:
                return self._create_wav_data(audio_data, sample_rate, sample_width, channels)
        return None

    def _create_synthesis_request(self, text: str) -> Synthesize:
        """Create a synthesis request with optional voice parameters."""
        synthesize_event = Synthesize(text=text)
        if (
            self.wyoming_tts_config.wyoming_voice
            or self.wyoming_tts_config.wyoming_tts_language
            or self.wyoming_tts_config.wyoming_speaker
        ):
            synthesize_event.voice = SynthesizeVoice(
                name=self.wyoming_tts_config.wyoming_voice,
                language=self.wyoming_tts_config.wyoming_tts_language,
                speaker=self.wyoming_tts_config.wyoming_speaker,
            )
        return synthesize_event

    async def _process_audio_events(
        self,
        client: AsyncClient,
    ) -> tuple[bytes, int | None, int | None, int | None]:
        """Process audio events from TTS server and return audio data with metadata."""
        audio_data = io.BytesIO()
        sample_rate, sample_width, channels = None, None, None
        while True:
            event = await client.read_event()
            if event is None:
                break
            if AudioStart.is_type(event.type):
                audio_start = AudioStart.from_event(event)
                sample_rate, sample_width, channels = (
                    audio_start.rate,
                    audio_start.width,
                    audio_start.channels,
                )
            elif AudioChunk.is_type(event.type):
                audio_data.write(AudioChunk.from_event(event).audio)
            elif AudioStop.is_type(event.type):
                break
        return audio_data.getvalue(), sample_rate, sample_width, channels

    def _create_wav_data(
        self,
        audio_data: bytes,
        sample_rate: int,
        sample_width: int,
        channels: int,
    ) -> bytes:
        """Convert raw audio data to WAV format."""
        wav_data = io.BytesIO()
        with wave.open(wav_data, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data)
        return wav_data.getvalue()


class WyomingWakeWordService(WakeWordService):
    """Wake word detection service using a Wyoming wake word server."""

    def __init__(
        self,
        wake_word_config: config.WakeWord,
        logger: logging.Logger,
        queue: asyncio.Queue,
        *,
        live: Live | None = None,
        quiet: bool = False,
    ) -> None:
        """Initialize the WyomingWakeWordService."""
        self.wake_word_config = wake_word_config
        self.logger = logger
        self.queue = queue
        self.live = live
        self.quiet = quiet

    async def detect(self) -> str | None:
        """Detect the wake word."""
        async with wyoming_client_context(
            self.wake_word_config.wake_server_ip,
            self.wake_word_config.wake_server_port,
            "wake word",
            self.logger,
            quiet=self.quiet,
        ) as client:
            await client.write_event(Detect(names=[self.wake_word_config.wake_word_name]).event())
            _send_task, recv_task = await manage_send_receive_tasks(
                self._send_audio_from_queue_for_wake_detection(client),
                self._receive_wake_detection(client),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if recv_task.done() and not recv_task.cancelled():
                return recv_task.result()
        return None

    async def _send_audio_from_queue_for_wake_detection(self, client: AsyncClient) -> None:
        """Read from a queue and send to Wyoming wake word server."""
        await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())
        try:
            await read_from_queue(
                queue=self.queue,
                chunk_handler=lambda chunk: client.write_event(
                    AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event(),
                ),
                logger=self.logger,
            )
        finally:
            if client._writer is not None:
                await client.write_event(AudioStop().event())

    async def _receive_wake_detection(self, client: AsyncClient) -> str | None:
        """Receive wake word detection events."""
        while True:
            event = await client.read_event()
            if event is None:
                break
            if Detection.is_type(event.type):
                return Detection.from_event(event).name
            if NotDetected.is_type(event.type):
                break
        return None
