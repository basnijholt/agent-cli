"""Wyoming TTS Client for converting text to speech."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path  # noqa: TC003

import typer

import agent_cli.agents._cli_options as opts
from agent_cli import process_manager
from agent_cli.agents._config import (
    FileConfig,
    GeneralConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingTTSConfig,
)
from agent_cli.agents._tts_common import handle_tts_playback
from agent_cli.audio import pyaudio_context, setup_devices
from agent_cli.cli import app, setup_logging
from agent_cli.utils import (
    get_clipboard_text,
    maybe_live,
    print_input_panel,
    stop_or_status_or_toggle,
)

LOGGER = logging.getLogger()


async def _async_main(
    *,
    general_cfg: GeneralConfig,
    text: str | None,
    tts_config: TTSConfig,
    file_config: FileConfig,
) -> None:
    """Async entry point for the speak command."""
    with pyaudio_context() as p:
        # We only use setup_devices for its output device handling
        device_info = setup_devices(p, general_cfg, None, tts_config)
        if device_info is None:
            return
        _, _, output_device_index = device_info
        tts_config.output_device_index = output_device_index

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
                tts_config=tts_config,
                save_file=file_config.save_file,
                quiet=general_cfg.quiet,
                logger=LOGGER,
                play_audio=not file_config.save_file,  # Don't play if saving to file
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
    wyoming_tts_ip: str = opts.WYOMING_TTS_SERVER_IP,
    wyoming_tts_port: int = opts.WYOMING_TTS_SERVER_PORT,
    wyoming_voice: str | None = opts.WYOMING_VOICE_NAME,
    wyoming_tts_language: str | None = opts.WYOMING_TTS_LANGUAGE,
    wyoming_speaker: str | None = opts.WYOMING_SPEAKER,
    # OpenAI
    openai_tts_model: str = opts.OPENAI_TTS_MODEL,
    openai_tts_voice: str = opts.OPENAI_TTS_VOICE,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    # --- General Options ---
    list_devices: bool = opts.LIST_DEVICES,
    save_file: Path | None = opts.SAVE_FILE,
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Convert text to speech using Wyoming or OpenAI TTS server."""
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
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
    with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
        # --- TTS Config ---
        wyoming_config = WyomingTTSConfig(
            server_ip=wyoming_tts_ip,
            server_port=wyoming_tts_port,
            voice_name=wyoming_voice,
            language=wyoming_tts_language,
            speaker=wyoming_speaker,
        )
        openai_config = OpenAITTSConfig(
            model=openai_tts_model,
            voice=openai_tts_voice,
            api_key=openai_api_key,
        )
        tts_config = TTSConfig(
            enabled=True,  # Implied for speak command
            provider=tts_provider,  # type: ignore[arg-type]
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            speed=tts_speed,
            local=wyoming_config,
            openai=openai_config,
        )
        file_config = FileConfig(save_file=save_file, history_dir=None, last_n_messages=0)

        asyncio.run(
            _async_main(
                general_cfg=general_cfg,
                text=text,
                tts_config=tts_config,
                file_config=file_config,
            ),
        )
