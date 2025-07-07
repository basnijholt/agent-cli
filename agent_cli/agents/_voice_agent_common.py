r"""Common functionalities for voice-based agents."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import pyperclip

from agent_cli import asr
from agent_cli.agents._tts_common import handle_tts_playback
from agent_cli.audio import (
    input_device,
    list_input_devices,
    list_output_devices,
    output_device,
    pyaudio_context,
)
from agent_cli.llm import process_and_update_clipboard
from agent_cli.utils import (
    InteractiveStopEvent,
    get_clipboard_text,
    maybe_live,
    print_device_index,
    print_input_panel,
    print_with_style,
    signal_handling_context,
)

if TYPE_CHECKING:
    import pyaudio
    from rich.live import Live

    from agent_cli.agents._config import (
        ASRConfig,
        FileConfig,
        GeneralConfig,
        LLMConfig,
        TTSConfig,
        WakeWordConfig,
    )

LOGGER = logging.getLogger()


RecordingFunc = Callable[
    ["pyaudio.PyAudio", int | None, InteractiveStopEvent, logging.Logger],
    Awaitable[bytes | None],
]


def _setup_devices(
    p: pyaudio.PyAudio,
    asr_config: ASRConfig,
    tts_config: TTSConfig,
    quiet: bool,
) -> tuple[int | None, str | None, int | None] | None:
    """Handle device listing and setup."""
    if asr_config.list_input_devices:
        list_input_devices(p, not quiet)
        return None

    if tts_config.list_output_devices:
        list_output_devices(p, not quiet)
        return None

    # Setup input device
    input_device_index, input_device_name = input_device(
        p,
        asr_config.input_device_name,
        asr_config.input_device_index,
    )
    if not quiet:
        print_device_index(input_device_index, input_device_name)

    # Setup output device for TTS if enabled
    tts_output_device_index = tts_config.output_device_index
    if tts_config.enabled and (tts_config.output_device_name or tts_config.output_device_index):
        tts_output_device_index, tts_output_device_name = output_device(
            p,
            tts_config.output_device_name,
            tts_config.output_device_index,
        )
        if tts_output_device_index is not None and not quiet:
            msg = f"🔊 TTS output device [bold yellow]{tts_output_device_index}[/bold yellow] ([italic]{tts_output_device_name}[/italic])"
            print_with_style(msg)

    return input_device_index, input_device_name, tts_output_device_index


async def _get_instruction_from_audio(
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


async def _process_instruction_and_respond(
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


async def async_main_voice_agent(
    *,
    # Functions
    recording_func: RecordingFunc,
    get_original_text_func: Callable[[], str | None] | None = None,
    # Configs
    general_cfg: GeneralConfig,
    asr_config: ASRConfig,
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    file_config: FileConfig,
    wake_word_config: WakeWordConfig | None = None,
    # Prompts
    system_prompt: str,
    agent_instructions: str,
) -> None:
    """Main async function for voice agents."""
    with (
        maybe_live(not general_cfg.quiet) as live,
        signal_handling_context(LOGGER, general_cfg.quiet) as main_stop_event,
    ):
        while not main_stop_event.is_set():
            with pyaudio_context() as p:
                device_info = _setup_devices(p, asr_config, tts_config, general_cfg.quiet)
                if device_info is None:
                    return
                input_device_index, _, tts_output_device_index = device_info

                original_text = (
                    get_original_text_func() if get_original_text_func else get_clipboard_text()
                )
                if original_text is None:
                    return

                if not general_cfg.quiet and original_text:
                    print_input_panel(original_text, title="📝 Text to Process")

                audio_data = await recording_func(
                    p,
                    input_device_index,
                    main_stop_event,
                    LOGGER,
                )

            if not audio_data:
                if not general_cfg.quiet:
                    print_with_style("No audio recorded", style="yellow")
                continue

            if main_stop_event.is_set():
                break

            instruction = await _get_instruction_from_audio(
                audio_data,
                asr_config,
                LOGGER,
                general_cfg.quiet,
            )
            if not instruction:
                continue

            await _process_instruction_and_respond(
                instruction=instruction,
                original_text=original_text,
                general_cfg=general_cfg,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
                system_prompt=system_prompt,
                agent_instructions=agent_instructions,
                tts_output_device_index=tts_output_device_index,
                live=live,
                logger=LOGGER,
            )

            if not general_cfg.quiet:
                print_with_style("✨ Ready for next command...", style="green")

            # For non-looping agents, break after one cycle
            if not getattr(wake_word_config, "wake_word_name", False):
                break
