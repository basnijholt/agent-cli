"""Shared TTS utilities for speak and voice-edit commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli import tts
from agent_cli.utils import InteractiveStopEvent, print_with_style

if TYPE_CHECKING:
    import logging

    from rich.live import Live

    from agent_cli.agents import config


async def _save_audio_file(
    audio_data: bytes,
    save_file: Path,
    quiet: bool,
    logger: logging.Logger,
    *,
    description: str = "Audio",
) -> None:
    try:
        save_path = Path(save_file)
        await asyncio.to_thread(save_path.write_bytes, audio_data)
        if not quiet:
            print_with_style(f"💾 {description} saved to {save_file}")
        logger.info("%s saved to %s", description, save_file)
    except (OSError, PermissionError) as e:
        logger.exception("Failed to save %s", description.lower())
        if not quiet:
            print_with_style(
                f"❌ Failed to save {description.lower()}: {e}",
                style="red",
            )


async def handle_tts_playback(
    *,
    text: str,
    provider_config: config.ProviderSelection,
    audio_output_config: config.AudioOutput,
    wyoming_tts_config: config.WyomingTTS,
    openai_tts_config: config.OpenAITTS,
    openai_llm_config: config.OpenAILLM,
    save_file: Path | None,
    quiet: bool,
    logger: logging.Logger,
    play_audio: bool = True,
    status_message: str = "🔊 Speaking...",
    description: str = "Audio",
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> bytes | None:
    """Handle TTS synthesis, playback, and file saving."""
    try:
        if not quiet and status_message:
            print_with_style(status_message, style="blue")

        audio_data = await tts.speak_text(
            text=text,
            provider_config=provider_config,
            audio_output_config=audio_output_config,
            wyoming_tts_config=wyoming_tts_config,
            openai_tts_config=openai_tts_config,
            openai_llm_config=openai_llm_config,
            logger=logger,
            quiet=quiet,
            play_audio_flag=play_audio,
            stop_event=stop_event,
            live=live,
        )

        if save_file and audio_data:
            await _save_audio_file(
                audio_data,
                save_file,
                quiet,
                logger,
                description=description,
            )

        return audio_data

    except (OSError, ConnectionError, TimeoutError) as e:
        logger.warning("Failed TTS operation: %s", e)
        if not quiet:
            print_with_style(f"⚠️ TTS failed: {e}", style="yellow")
        return None
