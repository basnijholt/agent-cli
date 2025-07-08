"""Wyoming ASR Client for streaming microphone audio to a transcription server."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import agent_cli.agents._cli_options as opts
from agent_cli import asr
from agent_cli.agents._command_setup import CommandConfig, setup_command, with_process_management
from agent_cli.agents._config import ASRConfig
from agent_cli.agents._llm_common import process_with_llm
from agent_cli.agents._ui_common import (
    display_input_text,
    display_no_input_warning,
    display_output_with_clipboard,
)
from agent_cli.audio import pyaudio_context, setup_devices
from agent_cli.cli import app
from agent_cli.utils import (
    maybe_live,
    signal_handling_context,
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

INPUT_TEMPLATE = """
<original-text>
{text}
</original-text>
<instruction>
{instruction}
</instruction>
"""


async def _async_main(
    *,
    asr_config: ASRConfig,
    config: CommandConfig,
    llm_enabled: bool,
    p: pyaudio.PyAudio,
) -> None:
    """Async entry point, consuming parsed args."""
    time_start = time.monotonic()
    with maybe_live(not config.general_cfg.quiet) as live:
        with signal_handling_context(LOGGER, config.general_cfg.quiet) as stop_event:
            transcript = await asr.transcribe_live_audio(
                asr_provider=asr_config.provider,
                asr_server_ip=asr_config.server_ip,
                asr_server_port=asr_config.server_port,
                openai_api_key=asr_config.openai_api_key,
                whisper_model=asr_config.whisper_model,
                input_device_index=asr_config.input_device_index,
                logger=LOGGER,
                p=p,
                stop_event=stop_event,
                quiet=config.general_cfg.quiet,
                live=live,
            )
        elapsed = time.monotonic() - time_start

        if not transcript:
            display_no_input_warning("transcription", config.general_cfg)
            return

        # If LLM is enabled, process the transcript
        if llm_enabled and config.llm_config:
            display_input_text(
                transcript,
                title="📝 Raw Transcript",
                general_cfg=config.general_cfg,
            )

            result = await process_with_llm(
                transcript,
                config.llm_config,
                SYSTEM_PROMPT,
                AGENT_INSTRUCTIONS,
                INPUT_TEMPLATE.format(text=transcript, instruction=INSTRUCTION),
            )

            if result["success"]:
                display_output_with_clipboard(
                    result["output"],
                    original_text=transcript,
                    elapsed=elapsed + result["elapsed"],
                    title="📝 Cleaned Transcript",
                    success_message="✅ Cleaned transcript copied to clipboard!",
                    general_cfg=config.general_cfg,
                )
            else:
                # Fall back to raw transcript
                display_output_with_clipboard(
                    transcript,
                    elapsed=elapsed,
                    title="📝 Raw Transcript (LLM failed)",
                    success_message="⚠️ LLM processing failed. Raw transcript copied to clipboard.",
                    general_cfg=config.general_cfg,
                )
        else:
            # No LLM processing - just copy transcript
            display_output_with_clipboard(
                transcript,
                elapsed=elapsed,
                title="📝 Transcript",
                success_message="✅ Transcript copied to clipboard!"
                if config.general_cfg.clipboard
                else "",
                general_cfg=config.general_cfg,
            )


@app.command("transcribe")
def transcribe(
    *,
    # ASR
    input_device_index: int | None = opts.DEVICE_INDEX,
    input_device_name: str | None = opts.DEVICE_NAME,
    asr_provider: str = opts.ASR_PROVIDER,
    asr_server_ip: str = opts.ASR_SERVER_IP,
    asr_server_port: int = opts.ASR_SERVER_PORT,
    openai_api_key: str = opts.OPENAI_API_KEY,
    whisper_model: str = opts.WHISPER_MODEL,
    # LLM
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    llm_provider: str = opts.LLM_PROVIDER,
    llm: bool = opts.LLM,
    # Process control
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # General
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
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
    config = setup_command(
        process_name="transcribe",
        command_description="transcribe",
        stop=stop,
        status=status,
        toggle=toggle,
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=clipboard,
        model=model if llm else None,
        ollama_host=ollama_host if llm else None,
        llm_provider=llm_provider if llm else None,
        openai_api_key=openai_api_key,
    )

    if config is None:
        return

    with pyaudio_context() as p:
        asr_config = ASRConfig(
            provider=asr_provider,
            server_ip=asr_server_ip,
            server_port=asr_server_port,
            openai_api_key=openai_api_key,
            whisper_model=whisper_model,
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        )
        # We only use setup_devices for its input device handling
        device_info = setup_devices(
            p,
            config.general_cfg,
            asr_config,
            None,
        )
        if device_info is None:
            return
        input_device_index, _, _ = device_info
        asr_config.input_device_index = input_device_index

        # Use context manager for PID file management
        with with_process_management("transcribe"):
            asyncio.run(
                _async_main(
                    asr_config=asr_config,
                    config=config,
                    llm_enabled=llm,
                    p=p,
                ),
            )
