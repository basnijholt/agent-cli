"""Wyoming TTS Client for converting text to speech."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path  # noqa: TC003

import typer

from agent_cli import config, opts
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import pyaudio_context, setup_devices
from agent_cli.core.utils import (
    get_clipboard_text,
    maybe_live,
    print_command_line_args,
    print_input_panel,
    setup_logging,
    stop_or_status_or_toggle,
)
from agent_cli.services.tts import handle_tts_playback

LOGGER = logging.getLogger()


async def _async_main(
    *,
    general_cfg: config.General,
    text: str | None,
    provider_cfg: config.ProviderSelection,
    audio_out_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
) -> None:
    """Async entry point for the speak command."""
    with pyaudio_context() as p:
        # We only use setup_devices for its output device handling
        device_info = setup_devices(p, general_cfg, None, audio_out_cfg)
        if device_info is None:
            return
        _, _, output_device_index = device_info
        audio_out_cfg.output_device_index = output_device_index

        # Get text from argument or clipboard
        if text is None:
            text = get_clipboard_text(quiet=general_cfg.quiet)
            if not text:
                return
            if not general_cfg.quiet:
                print_input_panel(text, title="📋 Text from Clipboard")
        elif not general_cfg.quiet:
            print_input_panel(text, title="📝 Text to Speak")

        # Handle TTS playback and saving
        with maybe_live(not general_cfg.quiet) as live:
            await handle_tts_playback(
                text=text,
                provider_cfg=provider_cfg,
                audio_output_cfg=audio_out_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                save_file=general_cfg.save_file,
                quiet=general_cfg.quiet,
                logger=LOGGER,
                play_audio=not general_cfg.save_file,  # Don't play if saving to file
                status_message="🔊 Synthesizing speech...",
                description="Audio",
                live=live,
            )


@app.command("speak")
def speak(
    *,
    text: str | None = typer.Argument(
        None,
        help="Text to speak. Reads from clipboard if not provided.",
        rich_help_panel="General Options",
    ),
    # --- Provider Selection ---
    tts_provider: str = opts.TTS_PROVIDER,
    # --- TTS Configuration ---
    # General
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    tts_speed: float = opts.TTS_SPEED,
    # Wyoming (local service)
    tts_wyoming_ip: str = opts.TTS_WYOMING_IP,
    tts_wyoming_port: int = opts.TTS_WYOMING_PORT,
    tts_wyoming_voice: str | None = opts.TTS_WYOMING_VOICE,
    tts_wyoming_language: str | None = opts.TTS_WYOMING_LANGUAGE,
    tts_wyoming_speaker: str | None = opts.TTS_WYOMING_SPEAKER,
    # OpenAI
    tts_openai_model: str = opts.TTS_OPENAI_MODEL,
    tts_openai_voice: str = opts.TTS_OPENAI_VOICE,
    # Kokoro
    tts_kokoro_model: str = opts.TTS_KOKORO_MODEL,
    tts_kokoro_voice: str = opts.TTS_KOKORO_VOICE,
    tts_kokoro_host: str = opts.TTS_KOKORO_HOST,
    # --- General Options ---
    list_devices: bool = opts.LIST_DEVICES,
    save_file: Path | None = opts.SAVE_FILE,
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Convert text to speech using Wyoming or OpenAI TTS server."""
    if print_args:
        print_command_line_args(locals())
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        save_file=save_file,
    )
    process_name = "speak"
    if stop_or_status_or_toggle(
        process_name,
        "speak process",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    # Use context manager for PID file management
    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        provider_cfg = config.ProviderSelection(
            tts_provider=tts_provider,
            asr_provider="local",  # Not used
            llm_provider="local",  # Not used
        )
        audio_out_cfg = config.AudioOutput(
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            tts_speed=tts_speed,
            enable_tts=True,  # Implied for speak command
        )
        wyoming_tts_cfg = config.WyomingTTS(
            tts_wyoming_ip=tts_wyoming_ip,
            tts_wyoming_port=tts_wyoming_port,
            tts_wyoming_voice=tts_wyoming_voice,
            tts_wyoming_language=tts_wyoming_language,
            tts_wyoming_speaker=tts_wyoming_speaker,
        )
        openai_tts_cfg = config.OpenAITTS(
            tts_openai_model=tts_openai_model,
            tts_openai_voice=tts_openai_voice,
        )
        kokoro_tts_cfg = config.KokoroTTS(
            tts_kokoro_model=tts_kokoro_model,
            tts_kokoro_voice=tts_kokoro_voice,
            tts_kokoro_host=tts_kokoro_host,
        )

        asyncio.run(
            _async_main(
                general_cfg=general_cfg,
                text=text,
                provider_cfg=provider_cfg,
                audio_out_cfg=audio_out_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
            ),
        )
