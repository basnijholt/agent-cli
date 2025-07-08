"""Shared TTS utilities for speak and voice-assistant commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli import tts
from agent_cli.utils import InteractiveStopEvent, print_with_style

if TYPE_CHECKING:
    import logging

    from rich.live import Live


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
    text: str,
    *,
    service_provider: str,
    openai_api_key: str | None,
    tts_server_ip: str,
    tts_server_port: int,
    voice_name: str | None,
    tts_language: str | None,
    speaker: str | None,
    output_device_index: int | None,
    save_file: Path | None,
    quiet: bool,
    logger: logging.Logger,
    play_audio: bool = True,
    status_message: str = "🔊 Speaking...",
    description: str = "Audio",
    stop_event: InteractiveStopEvent | None = None,
    speed: float = 1.0,
    live: Live,
) -> bytes | None:
    """Handle TTS synthesis, playback, and file saving."""
    try:
        if not quiet and status_message:
            print_with_style(status_message, style="blue")

        audio_data = await tts.speak_text(
            text=text,
            service_provider=service_provider,
            openai_api_key=openai_api_key,
            tts_server_ip=tts_server_ip,
            tts_server_port=tts_server_port,
            logger=logger,
            voice_name=voice_name,
            language=tts_language,
            speaker=speaker,
            output_device_index=output_device_index,
            quiet=quiet,
            play_audio_flag=play_audio,
            stop_event=stop_event,
            speed=speed,
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
