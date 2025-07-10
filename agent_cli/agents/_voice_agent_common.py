r"""Common functionalities for voice-based agents."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pyperclip

from agent_cli.core.utils import print_input_panel, print_with_style
from agent_cli.services import asr
from agent_cli.services.llm import process_and_update_clipboard
from agent_cli.services.tts import handle_tts_playback

if TYPE_CHECKING:
    from rich.live import Live

    from agent_cli import config

LOGGER = logging.getLogger()


async def get_instruction_from_audio(
    *,
    audio_data: bytes,
    provider_config: config.ProviderSelection,
    audio_input_config: config.AudioInput,
    wyoming_asr_config: config.WyomingASR,
    openai_asr_config: config.OpenAIASR,
    ollama_config: config.Ollama,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    quiet: bool,
) -> str | None:
    """Transcribe audio data and return the instruction."""
    try:
        start_time = time.monotonic()
        transcriber = asr.get_recorded_audio_transcriber(provider_config)
        instruction = await transcriber(
            audio_data=audio_data,
            provider_config=provider_config,
            audio_input_config=audio_input_config,
            wyoming_asr_config=wyoming_asr_config,
            openai_asr_config=openai_asr_config,
            ollama_config=ollama_config,
            openai_llm_config=openai_llm_config,
            logger=logger,
            quiet=quiet,
        )
        elapsed = time.monotonic() - start_time

        if not instruction or not instruction.strip():
            if not quiet:
                print_with_style(
                    "No speech detected in recording",
                    style="yellow",
                )
            return None

        if not quiet:
            print_input_panel(
                instruction,
                title="🎯 Instruction",
                style="bold yellow",
                subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
            )

        return instruction

    except Exception as e:
        logger.exception("Failed to process audio with ASR")
        if not quiet:
            print_with_style(f"ASR processing failed: {e}", style="red")
        return None


async def process_instruction_and_respond(
    *,
    instruction: str,
    original_text: str,
    provider_config: config.ProviderSelection,
    general_config: config.General,
    ollama_config: config.Ollama,
    openai_llm_config: config.OpenAILLM,
    audio_output_config: config.AudioOutput,
    wyoming_tts_config: config.WyomingTTS,
    openai_tts_config: config.OpenAITTS,
    kokoro_tts_config: config.KokoroTTS,
    system_prompt: str,
    agent_instructions: str,
    live: Live | None,
    logger: logging.Logger,
) -> None:
    """Process instruction with LLM and handle TTS response."""
    # Process with LLM if clipboard mode is enabled
    if general_config.clipboard:
        await process_and_update_clipboard(
            system_prompt=system_prompt,
            agent_instructions=agent_instructions,
            provider_config=provider_config,
            ollama_config=ollama_config,
            openai_config=openai_llm_config,
            logger=logger,
            original_text=original_text,
            instruction=instruction,
            clipboard=general_config.clipboard,
            quiet=general_config.quiet,
            live=live,
        )

        # Handle TTS response if enabled
        if audio_output_config.enable_tts:
            response_text = pyperclip.paste()
            if response_text and response_text.strip():
                await handle_tts_playback(
                    text=response_text,
                    provider_config=provider_config,
                    audio_output_config=audio_output_config,
                    wyoming_tts_config=wyoming_tts_config,
                    openai_tts_config=openai_tts_config,
                    kokoro_tts_config=kokoro_tts_config,
                    openai_llm_config=openai_llm_config,
                    save_file=general_config.save_file,
                    quiet=general_config.quiet,
                    logger=logger,
                    play_audio=not general_config.save_file,
                    status_message="🔊 Speaking response...",
                    description="TTS audio",
                    live=live,
                )
