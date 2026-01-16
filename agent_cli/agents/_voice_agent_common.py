r"""Common functionalities for voice-based agents."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

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
    provider_cfg: config.ProviderSelection,
    audio_input_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    ollama_cfg: config.Ollama,
    logger: logging.Logger,
    quiet: bool,
) -> str | None:
    """Transcribe audio data and return the instruction."""
    try:
        start_time = time.monotonic()
        transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
        instruction = await transcriber(
            audio_data=audio_data,
            provider_cfg=provider_cfg,
            audio_input_cfg=audio_input_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
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
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    audio_output_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS | None = None,
    system_prompt: str,
    agent_instructions: str,
    live: Live | None,
    logger: logging.Logger,
) -> str | None:
    """Process instruction with LLM and handle TTS response.

    Returns the processed text, or None if processing failed.
    """
    result: str | None = None
    # Process with LLM if clipboard mode is enabled
    if general_cfg.clipboard:
        result = await process_and_update_clipboard(
            system_prompt=system_prompt,
            agent_instructions=agent_instructions,
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_cfg=openai_llm_cfg,
            gemini_cfg=gemini_llm_cfg,
            logger=logger,
            original_text=original_text,
            instruction=instruction,
            clipboard=general_cfg.clipboard,
            quiet=general_cfg.quiet,
            live=live,
        )

        # Handle TTS response if enabled
        if audio_output_cfg.enable_tts and result and result.strip():
            await handle_tts_playback(
                text=result,
                provider_cfg=provider_cfg,
                audio_output_cfg=audio_output_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                gemini_tts_cfg=gemini_tts_cfg,
                save_file=general_cfg.save_file,
                quiet=general_cfg.quiet,
                logger=logger,
                play_audio=not general_cfg.save_file,
                status_message="🔊 Speaking response...",
                description="TTS audio",
                live=live,
            )

    return result
