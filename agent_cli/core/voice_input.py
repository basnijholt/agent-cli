"""Voice input handling with VAD-based speech detection.

This module provides a shared voice input loop that can be used by both
the transcribe daemon and the interactive chat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from agent_cli import constants
from agent_cli.core.audio import StreamConfig, open_audio_stream

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_cli import config
    from agent_cli.core.vad import VoiceActivityDetector


class VoiceInputStatus(Enum):
    """Status of the voice input loop."""

    LISTENING = "listening"
    RECORDING = "recording"
    PROCESSING = "processing"
    PAUSED = "paused"
    READY = "ready"


@dataclass
class VoiceInputState:
    """State for voice input with pause support."""

    is_paused: bool = False
    accumulated_text: str = ""
    status: VoiceInputStatus = field(default=VoiceInputStatus.LISTENING)


class TranscriberProtocol(Protocol):
    """Protocol for audio transcription functions."""

    async def __call__(self, audio_data: bytes) -> str | None:
        """Transcribe audio data to text."""
        ...


async def run_voice_input_loop(  # noqa: PLR0912, PLR0915, C901
    *,
    vad: VoiceActivityDetector,
    transcriber: TranscriberProtocol,
    state: VoiceInputState,
    on_status_change: Callable[[VoiceInputStatus], None] | None = None,
    on_text_update: Callable[[str], None] | None = None,
    on_segment_ready: Callable[[bytes], Awaitable[None]] | None = None,
    stop_event: asyncio.Event,
    input_device_index: int | None = None,
    logger: logging.Logger | None = None,
    min_segment_duration_seconds: float = 0.3,
) -> None:
    """VAD-based voice input loop with pause support.

    This is a reusable voice input loop that:
    - Captures audio from the microphone
    - Uses VAD to detect speech segments
    - Transcribes segments and accumulates text
    - Supports pause/resume functionality

    Args:
        vad: Voice activity detector instance
        transcriber: Function to transcribe audio bytes to text
        state: Shared state object for pause control and text accumulation
        on_status_change: Callback when status changes
        on_text_update: Callback when accumulated text updates
        on_segment_ready: Callback when a segment is ready (before transcription)
        stop_event: Event to signal loop termination
        input_device_index: Audio input device index
        logger: Logger instance
        min_segment_duration_seconds: Minimum segment duration to process

    """
    if logger is None:
        logger = logging.getLogger(__name__)

    stream_config = StreamConfig(
        dtype=constants.AUDIO_FORMAT_STR,
        channels=constants.AUDIO_CHANNELS,
        rate=constants.AUDIO_RATE,
        kind="input",
        blocksize=constants.AUDIO_CHUNK_SIZE,
        device=input_device_index,
    )

    was_speaking = False

    def update_status(new_status: VoiceInputStatus) -> None:
        """Update status and notify callback."""
        if state.status != new_status:
            state.status = new_status
            if on_status_change:
                on_status_change(new_status)

    with open_audio_stream(stream_config) as stream:
        while not stop_event.is_set():
            # Handle pause state
            if state.is_paused:
                update_status(VoiceInputStatus.PAUSED)
                await asyncio.sleep(0.1)
                continue

            # Read audio chunk
            try:
                data, _ = await asyncio.to_thread(
                    stream.read,
                    constants.AUDIO_CHUNK_SIZE,
                )
                chunk = data.tobytes()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error reading audio stream")
                await asyncio.sleep(0.1)
                continue

            # Process through VAD
            is_speaking, segment = vad.process_chunk(chunk)

            # Update status based on VAD state
            if is_speaking and not was_speaking:
                update_status(VoiceInputStatus.RECORDING)
            elif not is_speaking and was_speaking and segment is None:
                # Brief pause detected, still might continue speaking
                pass

            was_speaking = is_speaking

            # Process completed segment
            if segment:
                duration = vad.get_segment_duration_seconds(segment)

                if duration < min_segment_duration_seconds:
                    logger.debug("Skipping very short segment: %.2fs", duration)
                    update_status(VoiceInputStatus.LISTENING)
                    continue

                logger.debug("Speech segment detected: %.2fs", duration)
                update_status(VoiceInputStatus.PROCESSING)

                # Notify segment ready callback
                if on_segment_ready:
                    await on_segment_ready(segment)

                # Transcribe
                try:
                    text = await transcriber(segment)
                    if text and text.strip():
                        # Append to accumulated text
                        if state.accumulated_text:
                            state.accumulated_text += " " + text.strip()
                        else:
                            state.accumulated_text = text.strip()

                        # Notify text update callback
                        if on_text_update:
                            on_text_update(state.accumulated_text)

                        logger.debug("Transcribed: %s", text.strip())
                except Exception:
                    logger.exception("Error transcribing segment")

                # After transcription, we're ready for more input or sending
                update_status(VoiceInputStatus.READY)

            elif not is_speaking and not state.is_paused:
                # Not speaking, not paused - listening for speech
                if state.accumulated_text:
                    update_status(VoiceInputStatus.READY)
                else:
                    update_status(VoiceInputStatus.LISTENING)

    # Flush any remaining audio
    final_segment = vad.flush()
    if final_segment:
        duration = vad.get_segment_duration_seconds(final_segment)
        if duration >= min_segment_duration_seconds:
            update_status(VoiceInputStatus.PROCESSING)
            try:
                text = await transcriber(final_segment)
                if text and text.strip():
                    if state.accumulated_text:
                        state.accumulated_text += " " + text.strip()
                    else:
                        state.accumulated_text = text.strip()
                    if on_text_update:
                        on_text_update(state.accumulated_text)
            except Exception:
                logger.exception("Error transcribing final segment")


def create_transcriber_from_config(
    provider_cfg: config.ProviderSelection,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    wyoming_asr_cfg: config.WyomingASR,
    logger: logging.Logger,
    *,
    quiet: bool = True,
) -> TranscriberProtocol:
    """Create a transcriber function from configuration objects.

    Returns a callable that takes audio bytes and returns transcribed text.
    """
    from agent_cli.services.asr import create_recorded_audio_transcriber  # noqa: PLC0415

    recorded_transcriber = create_recorded_audio_transcriber(provider_cfg)

    async def transcribe(audio_data: bytes) -> str | None:
        if provider_cfg.asr_provider == "openai":
            return await recorded_transcriber(
                audio_data,
                openai_asr_cfg,
                logger,
                quiet=quiet,
            )
        if provider_cfg.asr_provider == "gemini":
            return await recorded_transcriber(
                audio_data,
                gemini_asr_cfg,
                logger,
                quiet=quiet,
            )
        if provider_cfg.asr_provider == "wyoming":
            return await recorded_transcriber(
                audio_data=audio_data,
                wyoming_asr_cfg=wyoming_asr_cfg,
                logger=logger,
                quiet=quiet,
            )
        msg = f"Unsupported ASR provider: {provider_cfg.asr_provider}"
        raise NotImplementedError(msg)

    return transcribe
