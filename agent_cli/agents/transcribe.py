"""Wyoming ASR Client for streaming microphone audio to a transcription server."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import pyperclip

import agent_cli.agents._cli_options as opts
from agent_cli import asr, process_manager
from agent_cli.agents._config import ASRConfig, GeneralConfig, LLMConfig
from agent_cli.audio import pyaudio_context, setup_devices
from agent_cli.cli import app, setup_logging
from agent_cli.llm import process_and_update_clipboard
from agent_cli.utils import (
    maybe_live,
    print_input_panel,
    print_output_panel,
    print_with_style,
    signal_handling_context,
    stop_or_status_or_toggle,
)

if TYPE_CHECKING:
    import pyaudio

LOGGER = logging.getLogger()

SYSTEM_PROMPT = """
You are an AI transcription cleanup assistant. Your purpose is to improve and refine raw speech-to-text transcriptions by correcting errors, adding proper punctuation, and enhancing readability while preserving the original meaning and intent.

Your tasks include:
- Correcting obvious speech recognition errors and mishearing
- Adding appropriate punctuation (periods, commas, question marks, etc.)
- Fixing capitalization where needed
- Removing filler words, false starts, and repeated words when they clearly weren't intentional
- Improving sentence structure and flow while maintaining the speaker's voice and meaning
- Formatting the text for better readability

Important rules:
- Do not change the core meaning or content of the transcription
- Do not add information that wasn't spoken
- Do not remove content unless it's clearly an error or filler
- Return ONLY the cleaned-up text without any explanations or commentary
- Do not wrap your output in markdown or code blocks
"""

AGENT_INSTRUCTIONS = """
You will be given a block of raw transcribed text enclosed in <original-text> tags, and a cleanup instruction enclosed in <instruction> tags.

Your job is to process the transcribed text according to the instruction, which will typically involve:
- Correcting speech recognition errors
- Adding proper punctuation and capitalization
- Removing obvious filler words and false starts
- Improving readability while preserving meaning

Return ONLY the cleaned-up text with no additional formatting or commentary.
"""

INSTRUCTION = """
Please clean up this transcribed text by correcting any speech recognition errors, adding appropriate punctuation and capitalization, removing obvious filler words or false starts, and improving overall readability while preserving the original meaning and intent of the speaker.
"""


async def async_main(
    *,
    asr_config: ASRConfig,
    general_cfg: GeneralConfig,
    llm_config: LLMConfig,
    llm_enabled: bool,
    p: pyaudio.PyAudio,
) -> None:
    """Async entry point, consuming parsed args."""
    time_start = time.monotonic()
    with maybe_live(not general_cfg.quiet) as live:
        with signal_handling_context(LOGGER, general_cfg.quiet) as stop_event:
            transcript = await asr.transcribe_live_audio(
                asr_server_ip=asr_config.server_ip,
                asr_server_port=asr_config.server_port,
                input_device_index=asr_config.input_device_index,
                logger=LOGGER,
                p=p,
                stop_event=stop_event,
                quiet=general_cfg.quiet,
                live=live,
            )
        elapsed = time.monotonic() - time_start
        if llm_enabled and llm_config.model and llm_config.ollama_host and transcript:
            if not general_cfg.quiet:
                print_input_panel(
                    transcript,
                    title="📝 Raw Transcript",
                    subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
                )
            await process_and_update_clipboard(
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=AGENT_INSTRUCTIONS,
                model=llm_config.model,
                ollama_host=llm_config.ollama_host,
                logger=LOGGER,
                original_text=transcript,
                instruction=INSTRUCTION,
                clipboard=general_cfg.clipboard,
                quiet=general_cfg.quiet,
                live=live,
            )
            return

    # When not using LLM, show transcript in output panel for consistency
    if transcript:
        if general_cfg.quiet:
            # Quiet mode: print result to stdout for Keyboard Maestro to capture
            print(transcript)
        else:
            print_output_panel(
                transcript,
                title="📝 Transcript",
                subtitle="[dim]Copied to clipboard[/dim]" if general_cfg.clipboard else "",
            )

        if general_cfg.clipboard:
            pyperclip.copy(transcript)
            LOGGER.info("Copied transcript to clipboard.")
        else:
            LOGGER.info("Clipboard copy disabled.")
    else:
        LOGGER.info("Transcript empty.")
        if not general_cfg.quiet:
            print_with_style(
                "⚠️ No transcript captured.",
                style="yellow",
            )


@app.command("transcribe")
def transcribe(
    *,
    # ASR
    input_device_index: int | None = opts.DEVICE_INDEX,
    input_device_name: str | None = opts.DEVICE_NAME,
    list_input_devices: bool = opts.LIST_DEVICES,
    asr_server_ip: str = opts.ASR_SERVER_IP,
    asr_server_port: int = opts.ASR_SERVER_PORT,
    # LLM
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    llm: bool = opts.LLM,
    # Process control
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # General
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Wyoming ASR Client for streaming microphone audio to a transcription server.

    Usage:
    - Run in foreground: agent-cli transcribe --input-device-index 1
    - Run in background: agent-cli transcribe --input-device-index 1 &
    - Check status: agent-cli transcribe --status
    - Stop background process: agent-cli transcribe --stop
    """
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        clipboard=clipboard,
    )
    process_name = "transcribe"
    if stop_or_status_or_toggle(
        process_name,
        "transcribe",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    with pyaudio_context() as p:
        asr_config = ASRConfig(
            server_ip=asr_server_ip,
            server_port=asr_server_port,
            input_device_index=input_device_index,
            input_device_name=input_device_name,
            list_input_devices=list_input_devices,
        )
        # We only use setup_devices for its input device handling
        device_info = setup_devices(
            p,
            asr_config,
            None,
            quiet,
        )
        if device_info is None:
            return
        input_device_index, _, _ = device_info
        asr_config.input_device_index = input_device_index

        # Use context manager for PID file management
        with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
            llm_config = LLMConfig(model=model, ollama_host=ollama_host)

            asyncio.run(
                async_main(
                    asr_config=asr_config,
                    general_cfg=general_cfg,
                    llm_config=llm_config,
                    llm_enabled=llm,
                    p=p,
                ),
            )
