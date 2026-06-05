"""Module for Automatic Speech Recognition using Wyoming or OpenAI."""

from __future__ import annotations

import asyncio
import io
import json
import wave
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli import constants
from agent_cli.core.audio import (
    open_audio_stream,
    read_audio_stream,
    read_from_queue,
    setup_input_stream,
)
from agent_cli.core.audio_format import check_ffmpeg_available, convert_audio_to_wyoming_format
from agent_cli.core.utils import err_console, manage_send_receive_tasks
from agent_cli.services import (
    transcribe_audio_gemini,
    transcribe_audio_openai,
)
from agent_cli.services._wyoming_utils import wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable

    import sounddevice as sd
    from rich.live import Live
    from wyoming.client import AsyncClient

    from agent_cli import config
    from agent_cli.core.utils import InteractiveStopEvent


@dataclass(frozen=True)
class LivePreviewConfig:
    """Configuration for rolling transcription previews."""

    log_file: Path | None = None
    interval_seconds: float = 2.0
    window_seconds: float = 15.0
    min_audio_seconds: float = 1.0
    console: bool = False

    @property
    def max_audio_bytes(self) -> int:
        """Maximum number of PCM bytes to keep in the rolling preview window."""
        return int(
            self.window_seconds
            * constants.AUDIO_RATE
            * constants.AUDIO_CHANNELS
            * constants.AUDIO_FORMAT_WIDTH,
        )

    @property
    def min_audio_bytes(self) -> int:
        """Minimum number of PCM bytes before attempting a preview."""
        return int(
            self.min_audio_seconds
            * constants.AUDIO_RATE
            * constants.AUDIO_CHANNELS
            * constants.AUDIO_FORMAT_WIDTH,
        )


def _write_live_preview_event(
    log_file: Path,
    *,
    event_type: str,
    revision: int,
    text: str,
) -> None:
    """Append one live preview event to a JSONL log."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": event_type,
        "revision": revision,
        "text": text,
        "is_final": event_type == "final",
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _print_live_preview_event(
    *,
    event_type: str,
    revision: int,
    text: str,
) -> None:
    """Print one live preview event to the terminal."""
    label = "final" if event_type == "final" else f"live #{revision}"
    err_console.print(f"[dim]{label}:[/dim] {text}")


class LivePreviewStreamer:
    """Periodically transcribe a rolling audio window and write preview events."""

    def __init__(
        self,
        preview_config: LivePreviewConfig,
        *,
        wyoming_asr_cfg: config.WyomingASR,
        logger: logging.Logger,
        extra_instructions: str | None = None,
    ) -> None:
        """Initialize the preview streamer."""
        self.config = preview_config
        self.wyoming_asr_cfg = wyoming_asr_cfg
        self.logger = logger
        self.extra_instructions = extra_instructions
        self._audio = bytearray()
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._revision = 0
        self._last_text = ""

    def reset_log(self) -> None:
        """Clear the preview log for a new recording session."""
        if self.config.log_file is None:
            return
        self.config.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.log_file.write_text("", encoding="utf-8")

    async def add_chunk(self, chunk: bytes) -> None:
        """Add a microphone audio chunk to the rolling preview buffer."""
        async with self._lock:
            self._audio.extend(chunk)
            max_bytes = max(0, self.config.max_audio_bytes)
            if max_bytes and len(self._audio) > max_bytes:
                del self._audio[: len(self._audio) - max_bytes]

    async def run(self) -> None:
        """Run the periodic preview loop until stopped."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), self.config.interval_seconds)
                break
            except TimeoutError:
                pass

            try:
                await self.emit_partial()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Live transcription preview failed")

    async def emit_partial(self) -> None:
        """Transcribe the current rolling window and write a partial if changed."""
        snapshot = await self._audio_snapshot()
        if len(snapshot) < self.config.min_audio_bytes:
            return

        text = await _transcribe_recorded_audio_wyoming(
            audio_data=snapshot,
            wyoming_asr_cfg=self.wyoming_asr_cfg,
            logger=self.logger,
            quiet=True,
            extra_instructions=self.extra_instructions,
        )
        text = text.strip()
        if not text or text == self._last_text:
            return
        if self._stop_event.is_set():
            return

        self._revision += 1
        self._last_text = text
        self._publish_event(event_type="partial", revision=self._revision, text=text)

    def request_stop(self) -> None:
        """Stop partial preview emission without writing the final transcript."""
        self._stop_event.set()

    async def stop(self, final_text: str | None = None) -> None:
        """Stop previewing and optionally append the final transcript."""
        self.request_stop()
        final_text = (final_text or "").strip()
        if final_text:
            self._revision += 1
            self._publish_event(event_type="final", revision=self._revision, text=final_text)

    def _publish_event(self, *, event_type: str, revision: int, text: str) -> None:
        if self.config.log_file is not None:
            _write_live_preview_event(
                self.config.log_file,
                event_type=event_type,
                revision=revision,
                text=text,
            )
        if self.config.console:
            _print_live_preview_event(
                event_type=event_type,
                revision=revision,
                text=text,
            )

    async def _audio_snapshot(self) -> bytes:
        async with self._lock:
            return bytes(self._audio)


def _get_transcriptions_dir() -> Path:
    """Get the directory for storing transcription recordings."""
    config_dir = Path.home() / ".config" / "agent-cli" / "transcriptions"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _save_audio_to_file(audio_data: bytes, logger: logging.Logger) -> Path | None:
    """Save audio data to a WAV file with timestamp-based filename.

    Returns the path to the saved file, or None if saving failed.
    """
    try:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        filename = f"recording_{timestamp}.wav"
        filepath = _get_transcriptions_dir() / filename

        with wave.open(str(filepath), "wb") as wav_file:
            wav_file.setnchannels(constants.AUDIO_CHANNELS)
            wav_file.setsampwidth(constants.AUDIO_FORMAT_WIDTH)  # 16-bit audio
            wav_file.setframerate(constants.AUDIO_RATE)
            wav_file.writeframes(audio_data)

        logger.info("Saved audio recording to %s", filepath)
        return filepath
    except OSError:
        logger.exception("Failed to save audio recording")
        return None


def get_last_recording(index: int = 1) -> Path | None:
    """Get the path to a recent recording file.

    Args:
        index: Which recording to get (1 = most recent, 2 = second-to-last, etc.)
               Default is 1 (most recent).

    Returns:
        Path to the recording file, or None if not found.

    """
    if index < 1:
        return None

    transcriptions_dir = _get_transcriptions_dir()
    recording_files = sorted(transcriptions_dir.glob("recording_*.wav"))

    if recording_files and len(recording_files) >= index:
        # -1 for most recent, -2 for second-to-last, etc.
        return recording_files[-index]
    return None


def _load_raw_audio(filepath: Path, logger: logging.Logger) -> bytes | None:
    """Load raw audio bytes from file without conversion."""
    try:
        audio_data = filepath.read_bytes()
        logger.info("Loaded raw audio from %s (%d bytes)", filepath, len(audio_data))
        return audio_data
    except OSError:
        logger.exception("Failed to read audio file %s", filepath)
        return None


def _load_wav_pcm(filepath: Path, logger: logging.Logger) -> bytes | None:
    """Extract PCM frames from a WAV file."""
    try:
        with wave.open(str(filepath), "rb") as wav_file:
            audio_data = wav_file.readframes(wav_file.getnframes())
            logger.info("Loaded PCM audio from %s", filepath)
            return audio_data
    except (OSError, wave.Error):
        logger.exception("Failed to load audio from %s", filepath)
        return None


def load_audio_from_file(
    filepath: Path,
    logger: logging.Logger,
    *,
    convert_to_pcm: bool = True,
) -> bytes | None:
    """Load audio data from a file.

    For WAV files, extracts raw PCM frames directly.
    For other formats (mp3, m4a, ogg, flac, etc.), converts to PCM using ffmpeg.

    Args:
        filepath: Path to the audio file
        logger: Logger instance
        convert_to_pcm: If True, convert non-WAV files to PCM. If False, return raw file bytes.

    Returns:
        Audio data as bytes, or None if loading failed.

    """
    # If caller wants raw bytes (for APIs that handle conversion themselves)
    if not convert_to_pcm:
        return _load_raw_audio(filepath, logger)

    # WAV files: extract PCM directly
    if filepath.suffix.lower() == ".wav":
        return _load_wav_pcm(filepath, logger)

    # Other formats: convert to PCM using ffmpeg
    if not check_ffmpeg_available():
        logger.error("ffmpeg not found. Please install ffmpeg to transcribe non-WAV audio files.")
        return None

    try:
        audio_bytes = filepath.read_bytes()
        pcm_data = convert_audio_to_wyoming_format(audio_bytes, filepath.name)
        logger.info("Converted %s to PCM using ffmpeg", filepath)
        return pcm_data
    except (OSError, RuntimeError):
        logger.exception("Failed to convert %s", filepath)
        return None


def create_transcriber(
    provider_cfg: config.ProviderSelection,
    audio_input_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR | None = None,
) -> Callable[..., Awaitable[str | None]]:
    """Return the appropriate transcriber for live audio based on the provider."""
    if provider_cfg.asr_provider == "wyoming":
        # Wyoming has streaming support, uses its own implementation
        return partial(
            _transcribe_live_audio_wyoming,
            audio_input_cfg=audio_input_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
        )

    # OpenAI and Gemini use the buffered record-then-transcribe pattern
    if provider_cfg.asr_provider == "openai":
        return partial(
            _transcribe_live_audio_buffered,
            audio_input_cfg=audio_input_cfg,
            transcribe_fn=transcribe_audio_openai,
            transcribe_cfg=openai_asr_cfg,
            provider_name="OpenAI",
        )
    if provider_cfg.asr_provider == "gemini":
        if gemini_asr_cfg is None:
            msg = "Gemini ASR config is required when using gemini provider"
            raise ValueError(msg)
        return partial(
            _transcribe_live_audio_buffered,
            audio_input_cfg=audio_input_cfg,
            transcribe_fn=transcribe_audio_gemini,
            transcribe_cfg=gemini_asr_cfg,
            provider_name="Gemini",
        )
    msg = f"Unsupported ASR provider: {provider_cfg.asr_provider}"
    raise ValueError(msg)


def create_recorded_audio_transcriber(
    provider_cfg: config.ProviderSelection,
) -> Callable[..., Awaitable[str]]:
    """Return the appropriate transcriber for recorded audio based on the provider."""
    if provider_cfg.asr_provider == "openai":
        return transcribe_audio_openai
    if provider_cfg.asr_provider == "wyoming":
        return _transcribe_recorded_audio_wyoming
    if provider_cfg.asr_provider == "gemini":
        return transcribe_audio_gemini
    msg = f"Unsupported ASR provider: {provider_cfg.asr_provider}"
    raise ValueError(msg)


def _schedule_audio_level_callback(
    pending_tasks: set[asyncio.Task[None]],
    audio_level_callback: Callable[[bytes], None],
    chunk: bytes,
    logger: logging.Logger,
) -> None:
    """Run level callbacks off the event loop so UI metering cannot delay ASR sends."""

    async def run_callback() -> None:
        try:
            await asyncio.to_thread(audio_level_callback, chunk)
        except Exception:
            logger.exception("Audio level callback failed")

    task = asyncio.create_task(run_callback())
    pending_tasks.add(task)
    task.add_done_callback(pending_tasks.discard)


async def _finish_audio_level_callbacks(pending_tasks: set[asyncio.Task[None]]) -> None:
    """Wait for scheduled level callbacks to finish before returning."""
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)


async def _send_audio(
    client: AsyncClient,
    stream: sd.InputStream,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    live: Live,
    quiet: bool = False,
    save_recording: bool = True,
    initial_prompt: str | None = None,
    recording_path_callback: Callable[[Path], None] | None = None,
    audio_level_callback: Callable[[bytes], None] | None = None,
    live_preview_callback: Callable[[bytes], Awaitable[None]] | None = None,
) -> None:
    """Read from mic and send to Wyoming server."""
    from wyoming.asr import Transcribe  # noqa: PLC0415
    from wyoming.audio import AudioChunk, AudioStart, AudioStop  # noqa: PLC0415

    # Build context with initial_prompt if provided
    context = {"initial_prompt": initial_prompt} if initial_prompt else None
    await client.write_event(Transcribe(context=context).event())
    await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())

    # Buffer to save audio if requested
    audio_buffer = io.BytesIO() if save_recording else None
    pending_audio_level_tasks: set[asyncio.Task[None]] = set()

    async def send_chunk(chunk: bytes) -> None:
        """Send audio chunk to ASR server and optionally buffer it."""
        if audio_buffer is not None:
            audio_buffer.write(chunk)
        if audio_level_callback:
            _schedule_audio_level_callback(
                pending_audio_level_tasks,
                audio_level_callback,
                chunk,
                logger,
            )
        if live_preview_callback is not None:
            await live_preview_callback(chunk)
        await client.write_event(AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event())

    try:
        await read_audio_stream(
            stream=stream,
            stop_event=stop_event,
            chunk_handler=send_chunk,
            logger=logger,
            live=live,
            quiet=quiet,
            progress_message="Listening",
            progress_style="blue",
        )
    finally:
        try:
            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop")

            # Save the recording to disk if requested
            if save_recording and audio_buffer:
                audio_data = audio_buffer.getvalue()
                if audio_data:
                    saved_path = _save_audio_to_file(audio_data, logger)
                    if saved_path and recording_path_callback:
                        recording_path_callback(saved_path)
        finally:
            await _finish_audio_level_callbacks(pending_audio_level_tasks)


async def record_audio_to_buffer(queue: asyncio.Queue, logger: logging.Logger) -> bytes:
    """Record audio from a queue to a buffer."""
    audio_buffer = io.BytesIO()

    def buffer_chunk(chunk: bytes) -> None:
        """Buffer audio chunk."""
        audio_buffer.write(chunk)

    await read_from_queue(queue=queue, chunk_handler=buffer_chunk, logger=logger)

    return audio_buffer.getvalue()


async def _receive_transcript(
    client: AsyncClient,
    logger: logging.Logger,
    *,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
) -> str:
    """Receive transcription events and return the final transcript."""
    from wyoming.asr import (  # noqa: PLC0415
        Transcript,
        TranscriptChunk,
        TranscriptStart,
        TranscriptStop,
    )

    transcript_text = ""
    while True:
        event = await client.read_event()
        if event is None:
            logger.warning("Connection to ASR server lost.")
            break

        if Transcript.is_type(event.type):
            transcript = Transcript.from_event(event)
            transcript_text = transcript.text
            logger.info("Final transcript: %s", transcript_text)
            if final_callback:
                final_callback(transcript_text)
            break
        if TranscriptChunk.is_type(event.type):
            chunk = TranscriptChunk.from_event(event)
            logger.debug("Transcript chunk: %s", chunk.text)
            if chunk_callback:
                chunk_callback(chunk.text)
        elif TranscriptStart.is_type(event.type) or TranscriptStop.is_type(event.type):
            logger.debug("Received %s", event.type)
        else:
            logger.debug("Ignoring event type: %s", event.type)

    return transcript_text


async def record_audio_with_manual_stop(
    input_device_index: int | None,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    quiet: bool = False,
    live: Live | None = None,
    save_recording: bool = True,
    recording_path_callback: Callable[[Path], None] | None = None,
    audio_level_callback: Callable[[bytes], None] | None = None,
) -> bytes:
    """Record audio to a buffer using a manual stop signal.

    Args:
        input_device_index: Audio input device index
        stop_event: Event to stop recording
        logger: Logger instance
        quiet: If True, suppress console output
        live: Rich Live display for progress
        save_recording: If True, save the recording to disk
        recording_path_callback: Optional callback invoked with the saved WAV path.
        audio_level_callback: Optional callback invoked with each PCM chunk.

    Returns:
        The recorded audio data as bytes

    """
    audio_buffer = io.BytesIO()
    pending_audio_level_tasks: set[asyncio.Task[None]] = set()

    def buffer_chunk(chunk: bytes) -> None:
        """Buffer audio chunk."""
        audio_buffer.write(chunk)
        if audio_level_callback:
            _schedule_audio_level_callback(
                pending_audio_level_tasks,
                audio_level_callback,
                chunk,
                logger,
            )

    stream_config = setup_input_stream(input_device_index)
    with open_audio_stream(stream_config) as stream:
        try:
            await read_audio_stream(
                stream=stream,
                stop_event=stop_event,
                chunk_handler=buffer_chunk,
                logger=logger,
                live=live,
                quiet=quiet,
                progress_message="Recording",
                progress_style="green",
            )
        finally:
            await _finish_audio_level_callbacks(pending_audio_level_tasks)

    audio_data = audio_buffer.getvalue()

    # Save the recording to disk if requested
    if save_recording and audio_data:
        saved_path = _save_audio_to_file(audio_data, logger)
        if saved_path and recording_path_callback:
            recording_path_callback(saved_path)

    return audio_data


async def _transcribe_recorded_audio_wyoming(
    *,
    audio_data: bytes,
    wyoming_asr_cfg: config.WyomingASR,
    logger: logging.Logger,
    quiet: bool = False,
    extra_instructions: str | None = None,
    **_kwargs: object,
) -> str:
    """Process pre-recorded audio data with Wyoming ASR server."""
    from wyoming.asr import Transcribe  # noqa: PLC0415
    from wyoming.audio import AudioChunk, AudioStart, AudioStop  # noqa: PLC0415

    try:
        async with wyoming_client_context(
            wyoming_asr_cfg.asr_wyoming_ip,
            wyoming_asr_cfg.asr_wyoming_port,
            "ASR",
            logger,
            quiet=quiet,
        ) as client:
            # Get effective prompt and pass via context
            effective_prompt = wyoming_asr_cfg.get_effective_prompt(extra_instructions)
            context = {"initial_prompt": effective_prompt} if effective_prompt else None
            await client.write_event(Transcribe(context=context).event())
            await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())

            chunk_size = constants.AUDIO_CHUNK_SIZE * 2
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i : i + chunk_size]
                await client.write_event(
                    AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event(),
                )
                logger.debug("Sent %d byte(s) of audio", len(chunk))

            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop")

            return await _receive_transcript(client, logger)
    except (ConnectionRefusedError, Exception):
        logger.warning("Failed to connect to Wyoming ASR server")
        return ""


async def _transcribe_live_audio_wyoming(
    *,
    audio_input_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    logger: logging.Logger,
    stop_event: InteractiveStopEvent,
    live: Live,
    quiet: bool = False,
    save_recording: bool = True,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
    extra_instructions: str | None = None,
    recording_path_callback: Callable[[Path], None] | None = None,
    audio_level_callback: Callable[[bytes], None] | None = None,
    live_preview_config: LivePreviewConfig | None = None,
    **_kwargs: object,
) -> str | None:
    """Unified ASR transcription function."""
    live_preview = (
        LivePreviewStreamer(
            live_preview_config,
            wyoming_asr_cfg=wyoming_asr_cfg,
            logger=logger,
            extra_instructions=extra_instructions,
        )
        if live_preview_config is not None
        else None
    )
    live_preview_task: asyncio.Task[None] | None = None
    final_transcript: str | None = None
    try:
        async with wyoming_client_context(
            wyoming_asr_cfg.asr_wyoming_ip,
            wyoming_asr_cfg.asr_wyoming_port,
            "ASR",
            logger,
            quiet=quiet,
        ) as client:
            # Get effective prompt for Wyoming
            effective_prompt = wyoming_asr_cfg.get_effective_prompt(extra_instructions)
            if effective_prompt:
                logger.info("Using initial_prompt for Wyoming ASR: %s...", effective_prompt[:50])

            stream_config = setup_input_stream(audio_input_cfg.input_device_index)
            with open_audio_stream(stream_config) as stream:
                if live_preview is not None:
                    live_preview.reset_log()
                    live_preview_task = asyncio.create_task(live_preview.run())
                _, recv_task = await manage_send_receive_tasks(
                    _send_audio(
                        client,
                        stream,
                        stop_event,
                        logger,
                        live=live,
                        quiet=quiet,
                        save_recording=save_recording,
                        initial_prompt=effective_prompt,
                        recording_path_callback=recording_path_callback,
                        audio_level_callback=audio_level_callback,
                        live_preview_callback=live_preview.add_chunk if live_preview else None,
                    ),
                    _receive_transcript(
                        client,
                        logger,
                        chunk_callback=chunk_callback,
                        final_callback=final_callback,
                    ),
                    return_when=asyncio.ALL_COMPLETED,
                )
                result = recv_task.result()
                final_transcript = result
                return result
    except (ConnectionRefusedError, Exception):
        logger.warning("Failed to connect to Wyoming ASR server")
        return None
    finally:
        if live_preview is not None:
            live_preview.request_stop()
        if live_preview_task is not None:
            live_preview_task.cancel()
            with suppress(asyncio.CancelledError):
                await live_preview_task
        if live_preview is not None:
            await live_preview.stop(final_transcript)


async def _transcribe_live_audio_buffered(
    *,
    audio_input_cfg: config.AudioInput,
    transcribe_fn: Callable[..., Awaitable[str]],
    transcribe_cfg: config.OpenAIASR | config.GeminiASR,
    provider_name: str,
    logger: logging.Logger,
    stop_event: InteractiveStopEvent,
    live: Live,
    quiet: bool = False,
    save_recording: bool = True,
    extra_instructions: str | None = None,
    recording_path_callback: Callable[[Path], None] | None = None,
    audio_level_callback: Callable[[bytes], None] | None = None,
    **_kwargs: object,
) -> str | None:
    """Record audio to buffer, then transcribe.

    Used for providers (OpenAI, Gemini) that don't support streaming transcription.
    """
    audio_data = await record_audio_with_manual_stop(
        audio_input_cfg.input_device_index,
        stop_event,
        logger,
        quiet=quiet,
        live=live,
        save_recording=save_recording,
        recording_path_callback=recording_path_callback,
        audio_level_callback=audio_level_callback,
    )
    if not audio_data:
        return None
    try:
        return await transcribe_fn(
            audio_data,
            transcribe_cfg,
            logger,
            extra_instructions=extra_instructions,
        )
    except Exception:
        logger.exception("Error during %s transcription", provider_name)
        return ""
