r"""Common functionalities for voice-based agents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyperclip

from agent_cli import asr
from agent_cli.agents._tts_common import handle_tts_playback
from agent_cli.llm import process_and_update_clipboard
from agent_cli.utils import (
    print_input_panel,
    print_with_style,
)

if TYPE_CHECKING:
    from rich.live import Live

    from agent_cli.agents._config import (
        ASRConfig,
        FileConfig,
        GeneralConfig,
        LLMConfig,
        TTSConfig,
    )

LOGGER = logging.getLogger()


async def get_instruction_from_audio(
    audio_data: bytes,
    asr_config: ASRConfig,
    logger: logging.Logger,
    quiet: bool,
) -> str | None:
    """Transcribe audio data and return the instruction."""
    if not quiet:
        print_with_style("🔄 Processing recorded audio...", style="blue")

    try:
        # Send audio data to Wyoming ASR server for transcription
        instruction = await asr.transcribe_recorded_audio(
            audio_data,
            asr_server_ip=asr_config.server_ip,
            asr_server_port=asr_config.server_port,
            logger=logger,
            quiet=quiet,
        )

        if not instruction or not instruction.strip():
            if not quiet:
                print_with_style(
                    "No speech detected in recording",
                    style="yellow",
                )
            return None
        return instruction

    except Exception as e:
        logger.exception("Failed to process audio with ASR")
        if not quiet:
            print_with_style(f"ASR processing failed: {e}", style="red")
        return None


async def process_instruction_and_respond(
    instruction: str,
    original_text: str,
    general_cfg: GeneralConfig,
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    file_config: FileConfig,
    system_prompt: str,
    agent_instructions: str,
    tts_output_device_index: int | None,
    live: Live | None,
    logger: logging.Logger,
) -> None:
    """Process instruction with LLM and handle TTS response."""
    if not general_cfg.quiet:
        print_input_panel(
            instruction,
            title="🎯 Instruction",
            style="bold yellow",
        )

    # Process with LLM if clipboard mode is enabled
    if general_cfg.clipboard:
        await process_and_update_clipboard(
            system_prompt=system_prompt,
            agent_instructions=agent_instructions,
            model=llm_config.model,
            ollama_host=llm_config.ollama_host,
            logger=logger,
            original_text=original_text,
            instruction=instruction,
            clipboard=general_cfg.clipboard,
            quiet=general_cfg.quiet,
            live=live,
        )

        # Handle TTS response if enabled
        if tts_config.enabled:
            response_text = pyperclip.paste()
            if response_text and response_text.strip():
                await handle_tts_playback(
                    response_text,
                    tts_server_ip=tts_config.server_ip,
                    tts_server_port=tts_config.server_port,
                    voice_name=tts_config.voice_name,
                    tts_language=tts_config.language,
                    speaker=tts_config.speaker,
                    output_device_index=tts_output_device_index,
                    save_file=file_config.save_file,
                    quiet=general_cfg.quiet,
                    logger=logger,
                    play_audio=not file_config.save_file,
                    status_message="🔊 Speaking response...",
                    description="TTS audio",
                    speed=tts_config.speed,
                    live=live,
                )
