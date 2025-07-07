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
- Start the agent: wake-word-assistant --wake-word "ok_nabu" --input-device-index 1
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
from functools import partial
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

import agent_cli.agents._cli_options as opts
from agent_cli import asr, audio, process_manager, wake_word
from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
    WakeWordConfig,
)
from agent_cli.agents._voice_agent_common import async_main_voice_agent
from agent_cli.cli import app, setup_logging
from agent_cli.utils import (
    InteractiveStopEvent,
    print_with_style,
    stop_or_status_or_toggle,
)

if TYPE_CHECKING:
    import pyaudio
    from rich.live import Live

LOGGER = logging.getLogger()

# LLM Prompts for wake word assistant
SYSTEM_PROMPT = """\
You are a helpful voice assistant. Respond to user questions and commands in a conversational, friendly manner.

Keep your responses concise but informative. If the user asks you to perform an action that requires external tools or systems, explain what you would do if you had access to those capabilities.

Always be helpful, accurate, and engaging in your responses.
"""

AGENT_INSTRUCTIONS = """\
The user has spoken a voice command or question. Provide a helpful, conversational response.

If it's a question, answer it clearly and concisely.
If it's a command, explain what you would do or provide guidance on how to accomplish it.
If it's unclear, ask for clarification in a friendly way.

Respond as if you're having a natural conversation.
"""


async def _record_audio_with_wake_word(
    p: pyaudio.PyAudio,
    input_device_index: int | None,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    wake_word_config: WakeWordConfig,
    quiet: bool = False,
    live: Live | None = None,
) -> bytes | None:
    """Record audio to a buffer using wake word detection to start and stop."""
    if not quiet:
        print_with_style(
            f"👂 Listening for wake word: [bold yellow]{wake_word_config.wake_word_name}[/bold yellow]",
        )
        print_with_style(
            "Say the wake word to start recording, then say it again to stop and process.",
            style="dim",
        )

    stream_config = audio.setup_input_stream(input_device_index)
    with audio.open_pyaudio_stream(p, **stream_config) as stream:
        detected_word = await wake_word.detect_wake_word(
            wake_server_ip=wake_word_config.server_ip,
            wake_server_port=wake_word_config.server_port,
            wake_word_name=wake_word_config.wake_word_name,
            logger=logger,
            stream=stream,
            stop_event=stop_event,
            live=live,
            quiet=quiet,
        )

    if not detected_word or stop_event.is_set():
        return None

    if not quiet:
        print_with_style(
            f"✅ Wake word '{detected_word}' detected! Starting recording...",
            style="green",
        )

    # Re-open stream to clear buffer and ensure clean recording
    with audio.open_pyaudio_stream(p, **stream_config) as stream:
        # Tee the audio stream to two queues: one for recording, one for wake word detection
        async with audio.tee_audio_stream(stream, stop_event, logger) as tee:
            record_queue = tee.add_queue()
            wake_queue = tee.add_queue()

            record_task = asyncio.create_task(
                asr.record_audio_to_buffer(
                    record_queue,
                    logger,
                ),
            )

            stop_detected_word = await wake_word.detect_wake_word_from_queue(
                wake_server_ip=wake_word_config.server_ip,
                wake_server_port=wake_word_config.server_port,
                wake_word_name=wake_word_config.wake_word_name,
                logger=logger,
                queue=wake_queue,
                quiet=quiet,
            )

            # Stop the tee, which will signal the end of the stream to the queues
            await tee.stop()
            audio_data = await record_task

    if not stop_detected_word or stop_event.is_set():
        return None

    if not quiet:
        print_with_style(
            f"🛑 Wake word '{stop_detected_word}' detected! Stopping recording...",
            style="yellow",
        )

    return audio_data


def get_empty_text() -> str:
    """Return empty string, as this agent doesn't process existing text."""
    return ""


@app.command("wake-word-assistant")
def wake_word_assistant(
    *,
    # Wake word parameters
    wake_server_ip: str = opts.WAKE_WORD_SERVER_IP,
    wake_server_port: int = opts.WAKE_WORD_SERVER_PORT,
    wake_word_name: str = opts.WAKE_WORD_NAME,
    # ASR parameters
    input_device_index: int | None = opts.DEVICE_INDEX,
    input_device_name: str | None = opts.DEVICE_NAME,
    list_input_devices: bool = opts.LIST_DEVICES,
    asr_server_ip: str = opts.ASR_SERVER_IP,
    asr_server_port: int = opts.ASR_SERVER_PORT,
    # LLM parameters
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    # Process control
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # TTS parameters
    enable_tts: bool = opts.ENABLE_TTS,
    tts_server_ip: str = opts.TTS_SERVER_IP,
    tts_server_port: int = opts.TTS_SERVER_PORT,
    voice_name: str | None = opts.VOICE_NAME,
    tts_language: str | None = opts.TTS_LANGUAGE,
    speaker: str | None = opts.SPEAKER,
    tts_speed: float = opts.TTS_SPEED,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    list_output_devices_flag: bool = opts.LIST_OUTPUT_DEVICES,
    # Output
    save_file: Path | None = opts.SAVE_FILE,
    # General
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Wake word-based voice assistant using Wyoming wake word detection."""
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        clipboard=clipboard,
    )
    process_name = "wake-word-assistant"
    if stop_or_status_or_toggle(
        process_name,
        "wake word assistant",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
        wake_word_config = WakeWordConfig(
            server_ip=wake_server_ip,
            server_port=wake_server_port,
            wake_word_name=wake_word_name,
            input_device_index=input_device_index,
            input_device_name=input_device_name,
            list_input_devices=list_input_devices,
        )
        asr_config = ASRConfig(
            server_ip=asr_server_ip,
            server_port=asr_server_port,
            input_device_index=input_device_index,
            input_device_name=input_device_name,
            list_input_devices=list_input_devices,
        )
        llm_config = LLMConfig(model=model, ollama_host=ollama_host)
        tts_config = TTSConfig(
            enabled=enable_tts,
            server_ip=tts_server_ip,
            server_port=tts_server_port,
            voice_name=voice_name,
            language=tts_language,
            speaker=speaker,
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            list_output_devices=list_output_devices_flag,
            speed=tts_speed,
        )
        file_config = FileConfig(save_file=save_file)

        recording_func = partial(
            _record_audio_with_wake_word,
            wake_word_config=wake_word_config,
            quiet=general_cfg.quiet,
        )

        asyncio.run(
            async_main_voice_agent(
                recording_func=recording_func,
                get_original_text_func=get_empty_text,
                general_cfg=general_cfg,
                asr_config=asr_config,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
                wake_word_config=wake_word_config,
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=AGENT_INSTRUCTIONS,
            ),
        )
