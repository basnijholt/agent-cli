"""Wyoming ASR Client for streaming microphone audio to a transcription server."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

import pyperclip
import typer

from agent_cli import config, opts
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import pyaudio_context, setup_devices
from agent_cli.core.utils import (
    maybe_live,
    print_input_panel,
    print_output_panel,
    print_with_style,
    setup_logging,
    signal_handling_context,
    stop_or_status_or_toggle,
)
from agent_cli.services import asr
from agent_cli.services.llm import process_and_update_clipboard

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


async def _async_main(
    *,
    extra_instructions: str | None,
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    audio_in_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    llm_enabled: bool,
    p: pyaudio.PyAudio,
) -> None:
    """Async entry point, consuming parsed args."""
    start_time = time.monotonic()
    with maybe_live(not general_cfg.quiet) as live:
        with signal_handling_context(LOGGER, general_cfg.quiet) as stop_event:
            transcriber = asr.get_transcriber(
                provider_cfg,
                audio_in_cfg,
                wyoming_asr_cfg,
                openai_asr_cfg,
                openai_llm_cfg,
            )
            transcript = await transcriber(
                logger=LOGGER,
                p=p,
                stop_event=stop_event,
                quiet=general_cfg.quiet,
                live=live,
            )
        elapsed = time.monotonic() - start_time
        if llm_enabled and transcript:
            if not general_cfg.quiet:
                print_input_panel(
                    transcript,
                    title="📝 Raw Transcript",
                    subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
                )
            instructions = AGENT_INSTRUCTIONS
            if extra_instructions:
                instructions += f"\n\n{extra_instructions}"

            await process_and_update_clipboard(
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=instructions,
                provider_config=provider_cfg,
                ollama_config=ollama_cfg,
                openai_config=openai_llm_cfg,
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
    extra_instructions: str | None = typer.Option(
        None,
        "--extra-instructions",
        help="Additional instructions for the LLM to process the transcription.",
    ),
    # --- Provider Selection ---
    asr_provider: str = opts.ASR_PROVIDER,
    llm_provider: str = opts.LLM_PROVIDER,
    # --- ASR (Audio) Configuration ---
    input_device_index: int | None = opts.INPUT_DEVICE_INDEX,
    input_device_name: str | None = opts.INPUT_DEVICE_NAME,
    wyoming_asr_ip: str = opts.WYOMING_ASR_SERVER_IP,
    wyoming_asr_port: int = opts.WYOMING_ASR_SERVER_PORT,
    openai_asr_model: str = opts.OPENAI_ASR_MODEL,
    # --- LLM Configuration ---
    ollama_model: str = opts.OLLAMA_MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    openai_llm_model: str = opts.OPENAI_LLM_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    llm: bool = opts.LLM,
    # --- Process Management ---
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # --- General Options ---
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Wyoming ASR Client for streaming microphone audio to a transcription server."""
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
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
        provider_cfg = config.ProviderSelection(
            asr_provider=asr_provider,
            llm_provider=llm_provider,
            tts_provider="local",  # Not used
        )
        audio_in_cfg = config.AudioInput(
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        )
        wyoming_asr_cfg = config.WyomingASR(
            wyoming_asr_ip=wyoming_asr_ip,
            wyoming_asr_port=wyoming_asr_port,
        )
        openai_asr_cfg = config.OpenAIASR(
            openai_asr_model=openai_asr_model,
        )
        ollama_cfg = config.Ollama(ollama_model=ollama_model, ollama_host=ollama_host)
        openai_llm_cfg = config.OpenAILLM(
            openai_llm_model=openai_llm_model,
            openai_api_key=openai_api_key,
        )

        # We only use setup_devices for its input device handling
        device_info = setup_devices(p, general_cfg, audio_in_cfg, None)
        if device_info is None:
            return
        input_device_index, _, _ = device_info
        audio_in_cfg.input_device_index = input_device_index

        # Use context manager for PID file management
        with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
            asyncio.run(
                _async_main(
                    extra_instructions=extra_instructions,
                    provider_cfg=provider_cfg,
                    general_cfg=general_cfg,
                    audio_in_cfg=audio_in_cfg,
                    wyoming_asr_cfg=wyoming_asr_cfg,
                    openai_asr_cfg=openai_asr_cfg,
                    ollama_cfg=ollama_cfg,
                    openai_llm_cfg=openai_llm_cfg,
                    llm_enabled=llm,
                    p=p,
                ),
            )
