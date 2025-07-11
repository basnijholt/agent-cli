r"""Wake word-based voice assistant that records when wake word is detected.

This agent uses Wyoming wake word detection to implement a hands-free voice assistant that:
1. Continuously listens for a wake word
2. When the wake word is detected, starts recording user speech
3. When the wake word is detected again, stops recording and processes the speech
4. Sends the recorded speech to ASR for transcription
5. Optionally processes the transcript with an LLM and speaks the response

WORKFLOW:
1. Agent starts listening for the specified wake word
2. First wake word detection -> start recording user speech
3. Second wake word detection -> stop recording and process the speech
4. Transcribe the recorded speech using Wyoming ASR
5. Optionally process with LLM and respond with TTS

USAGE:
- Start the agent: assistant --wake-word "ok_nabu" --input-device-index 1
- The agent runs continuously until stopped with Ctrl+C or --stop
- Uses background process management for daemon-like operation

REQUIREMENTS:
- Wyoming wake word server (e.g., wyoming-openwakeword)
- Wyoming ASR server (e.g., wyoming-whisper)
- Optional: Wyoming TTS server for responses
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from agent_cli import config, opts
from agent_cli.agents._voice_agent_common import (
    get_instruction_from_audio,
    process_instruction_and_respond,
)
from agent_cli.cli import app
from agent_cli.core import audio, process
from agent_cli.core.audio import pyaudio_context, setup_devices
from agent_cli.core.utils import (
    InteractiveStopEvent,
    maybe_live,
    print_command_line_args,
    print_with_style,
    setup_logging,
    signal_handling_context,
    stop_or_status_or_toggle,
)
from agent_cli.services import asr
from agent_cli.services.wake_word import create_wake_word_detector

if TYPE_CHECKING:
    import pyaudio
    from rich.live import Live

LOGGER = logging.getLogger()

WAKE_WORD_VARIATIONS = {
    "ok_nabu": ["ok nabu", "okay nabu", "okay, nabu", "ok, nabu", "ok naboo", "okay naboo"],
    "alexa": ["alexa"],
    "hey_jarvis": ["hey jarvis"],
}

# LLM Prompts for wake word assistant
SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful voice assistant. Respond to user questions and commands in a conversational, friendly manner.

The user is using a wake word to start and stop the recording, so the wake word will always appear at the END of the transcription.
The wake word is "{wake_word}". You should ignore the wake word and any variations of it (e.g., "{variations}") when processing the user's command.

Keep your responses concise but informative. If the user asks you to perform an action that requires external tools or systems, explain what you would do if you had access to those capabilities.

Always be helpful, accurate, and engaging in your responses.
"""

AGENT_INSTRUCTIONS_TEMPLATE = """\
The user has spoken a voice command or question. The user is using a wake word to start and stop the recording. The wake word is "{wake_word}". You should ignore the wake word and any variations of it (e.g., "{variations}") when processing the user's command.

Provide a helpful, conversational response.

If it's a question, answer it clearly and concisely.
If it's a command, explain what you would do or provide guidance on how to accomplish it.
If it's unclear, ask for clarification in a friendly way.

Respond as if you're having a natural conversation.
"""


async def _record_audio_with_wake_word(
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    wake_word_cfg: config.WakeWord,
    quiet: bool = False,
    live: Live | None = None,
) -> bytes | None:
    """Record audio to a buffer using wake word detection to start and stop."""
    if not quiet:
        print_with_style(
            f"👂 Listening for wake word: [bold yellow]{wake_word_cfg.wake_word}[/bold yellow]",
        )
        print_with_style(
            "Say the wake word to start recording, then say it again to stop and process.",
            style="dim",
        )

    async with audio.tee_audio_stream(stream, stop_event, logger) as tee:
        # Create a queue for wake word detection
        wake_queue = await tee.add_queue()

        detector = create_wake_word_detector(wake_word_cfg)
        detected_word = await detector(
            logger=logger,
            queue=wake_queue,
            quiet=quiet,
            live=live,
        )

        if not detected_word or stop_event.is_set():
            # Clean up the queue if we exit early
            await tee.remove_queue(wake_queue)
            return None

        if not quiet:
            print_with_style(
                f"✅ Wake word '{detected_word}' detected! Starting recording...",
                style="green",
            )

        # Add a new queue for recording
        record_queue = await tee.add_queue()
        record_task = asyncio.create_task(asr.record_audio_to_buffer(record_queue, logger))

        # Use the same wake_queue for stop-word detection
        stop_detected_word = await detector(
            logger=logger,
            queue=wake_queue,
            quiet=quiet,
            live=live,
            progress_message="Recording... (say wake word to stop)",
        )

        # Stop the recording task by removing its queue
        await tee.remove_queue(record_queue)
        audio_data = await record_task

        # Clean up the wake queue
        await tee.remove_queue(wake_queue)

    if not stop_detected_word or stop_event.is_set():
        return None

    if not quiet:
        print_with_style(
            f"🛑 Wake word '{stop_detected_word}' detected! Stopping recording...",
            style="yellow",
        )

    return audio_data


async def _async_main(
    *,
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    audio_in_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    audio_out_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    wake_word_cfg: config.WakeWord,
    system_prompt: str,
    agent_instructions: str,
    live: Live | None,
) -> None:
    """Core asynchronous logic for the wake word assistant."""
    with pyaudio_context() as p:
        device_info = setup_devices(p, general_cfg, audio_in_cfg, audio_out_cfg)
        if device_info is None:
            return
        input_device_index, _, tts_output_device_index = device_info
        audio_in_cfg.input_device_index = input_device_index
        audio_out_cfg.output_device_index = tts_output_device_index

        stream_kwargs = audio.setup_input_stream(input_device_index)
        with (
            audio.open_pyaudio_stream(p, **stream_kwargs) as stream,
            signal_handling_context(LOGGER, general_cfg.quiet) as stop_event,
        ):
            while not stop_event.is_set():
                audio_data = await _record_audio_with_wake_word(
                    stream,
                    stop_event,
                    LOGGER,
                    wake_word_cfg=wake_word_cfg,
                    quiet=general_cfg.quiet,
                    live=live,
                )

                if not audio_data:
                    if not general_cfg.quiet:
                        print_with_style("No audio recorded", style="yellow")
                    continue

                if stop_event.is_set():
                    break

                instruction = await get_instruction_from_audio(
                    audio_data=audio_data,
                    provider_cfg=provider_cfg,
                    audio_input_cfg=audio_in_cfg,
                    wyoming_asr_cfg=wyoming_asr_cfg,
                    openai_asr_cfg=openai_asr_cfg,
                    ollama_cfg=ollama_cfg,
                    logger=LOGGER,
                    quiet=general_cfg.quiet,
                )
                if not instruction:
                    continue

                await process_instruction_and_respond(
                    instruction=instruction,
                    original_text="",
                    provider_cfg=provider_cfg,
                    general_cfg=general_cfg,
                    ollama_cfg=ollama_cfg,
                    openai_llm_cfg=openai_llm_cfg,
                    gemini_llm_cfg=gemini_llm_cfg,
                    audio_output_cfg=audio_out_cfg,
                    wyoming_tts_cfg=wyoming_tts_cfg,
                    openai_tts_cfg=openai_tts_cfg,
                    kokoro_tts_cfg=kokoro_tts_cfg,
                    system_prompt=system_prompt,
                    agent_instructions=agent_instructions,
                    live=live,
                    logger=LOGGER,
                )

                if not general_cfg.quiet:
                    print_with_style("✨ Ready for next command...", style="green")


@app.command("assistant")
def assistant(
    *,
    # --- Provider Selection ---
    asr_provider: str = opts.ASR_PROVIDER,
    llm_provider: str = opts.LLM_PROVIDER,
    tts_provider: str = opts.TTS_PROVIDER,
    # --- Wake Word Configuration ---
    wake_server_ip: str = opts.WAKE_SERVER_IP,
    wake_server_port: int = opts.WAKE_SERVER_PORT,
    wake_word: str = opts.WAKE_WORD,
    # --- ASR (Audio) Configuration ---
    input_device_index: int | None = opts.INPUT_DEVICE_INDEX,
    input_device_name: str | None = opts.INPUT_DEVICE_NAME,
    asr_wyoming_ip: str = opts.ASR_WYOMING_IP,
    asr_wyoming_port: int = opts.ASR_WYOMING_PORT,
    asr_openai_model: str = opts.ASR_OPENAI_MODEL,
    # --- LLM Configuration ---
    llm_ollama_model: str = opts.LLM_OLLAMA_MODEL,
    llm_ollama_host: str = opts.LLM_OLLAMA_HOST,
    llm_openai_model: str = opts.LLM_OPENAI_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    llm_gemini_model: str = opts.LLM_GEMINI_MODEL,
    gemini_api_key: str | None = opts.GEMINI_API_KEY,
    # --- TTS Configuration ---
    enable_tts: bool = opts.ENABLE_TTS,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    tts_speed: float = opts.TTS_SPEED,
    tts_wyoming_ip: str = opts.TTS_WYOMING_IP,
    tts_wyoming_port: int = opts.TTS_WYOMING_PORT,
    tts_wyoming_voice: str | None = opts.TTS_WYOMING_VOICE,
    tts_wyoming_language: str | None = opts.TTS_WYOMING_LANGUAGE,
    tts_wyoming_speaker: str | None = opts.TTS_WYOMING_SPEAKER,
    tts_openai_model: str = opts.TTS_OPENAI_MODEL,
    tts_openai_voice: str = opts.TTS_OPENAI_VOICE,
    tts_kokoro_model: str = opts.TTS_KOKORO_MODEL,
    tts_kokoro_voice: str = opts.TTS_KOKORO_VOICE,
    tts_kokoro_host: str = opts.TTS_KOKORO_HOST,
    # --- Process Management ---
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # --- General Options ---
    save_file: Path | None = opts.SAVE_FILE,
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Wake word-based voice assistant using local or remote services."""
    if print_args:
        print_command_line_args(locals())
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=clipboard,
        save_file=save_file,
    )
    process_name = "assistant"
    if stop_or_status_or_toggle(
        process_name,
        "wake word assistant",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    with (
        process.pid_file_context(process_name),
        suppress(KeyboardInterrupt),
        maybe_live(not general_cfg.quiet) as live,
    ):
        provider_cfg = config.ProviderSelection(
            asr_provider=asr_provider,
            llm_provider=llm_provider,
            tts_provider=tts_provider,
        )
        audio_in_cfg = config.AudioInput(
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip=asr_wyoming_ip,
            asr_wyoming_port=asr_wyoming_port,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model=asr_openai_model,
            openai_api_key=openai_api_key,
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model=llm_ollama_model,
            llm_ollama_host=llm_ollama_host,
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=llm_openai_model,
            openai_api_key=openai_api_key,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model=llm_gemini_model,
            gemini_api_key=gemini_api_key,
        )
        audio_out_cfg = config.AudioOutput(
            enable_tts=enable_tts,
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            tts_speed=tts_speed,
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
            openai_api_key=openai_api_key,
        )
        kokoro_tts_cfg = config.KokoroTTS(
            tts_kokoro_model=tts_kokoro_model,
            tts_kokoro_voice=tts_kokoro_voice,
            tts_kokoro_host=tts_kokoro_host,
        )
        wake_word_cfg = config.WakeWord(
            wake_server_ip=wake_server_ip,
            wake_server_port=wake_server_port,
            wake_word=wake_word,
        )

        variations = ", ".join(WAKE_WORD_VARIATIONS.get(wake_word_cfg.wake_word, []))
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            wake_word=wake_word_cfg.wake_word,
            variations=variations,
        )
        agent_instructions = AGENT_INSTRUCTIONS_TEMPLATE.format(
            wake_word=wake_word_cfg.wake_word,
            variations=variations,
        )

        asyncio.run(
            _async_main(
                provider_cfg=provider_cfg,
                general_cfg=general_cfg,
                audio_in_cfg=audio_in_cfg,
                wyoming_asr_cfg=wyoming_asr_cfg,
                openai_asr_cfg=openai_asr_cfg,
                ollama_cfg=ollama_cfg,
                openai_llm_cfg=openai_llm_cfg,
                gemini_llm_cfg=gemini_llm_cfg,
                audio_out_cfg=audio_out_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                wake_word_cfg=wake_word_cfg,
                system_prompt=system_prompt,
                agent_instructions=agent_instructions,
                live=live,
            ),
        )
