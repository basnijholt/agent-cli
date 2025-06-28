r"""Interact with clipboard text via a voice command using Wyoming and an Ollama LLM.

This script combines functionalities from transcribe.py and autocorrect_ollama.py.

WORKFLOW:
1. The script starts and immediately copies the current content of the clipboard.
2. It then starts listening for a voice command via the microphone.
3. The user triggers a stop signal (e.g., via a Keyboard Maestro hotkey sending SIGINT).
4. The script stops recording and finalizes the transcription of the voice command.
5. It sends the original clipboard text and the transcribed command to a local LLM.
6. The LLM processes the text based on the instruction (either editing it or answering a question).
7. The resulting text is then copied back to the clipboard.

KEYBOARD MAESTRO INTEGRATION:
To create a hotkey toggle for this script, set up a Keyboard Maestro macro with:

1. Trigger: Hot Key (e.g., Cmd+Shift+A for "Assistant")

2. If/Then/Else Action:
   - Condition: Shell script returns success
   - Script: voice-assistant --status >/dev/null 2>&1

3. Then Actions (if process is running):
   - Display Text Briefly: "🗣️ Processing command..."
   - Execute Shell Script: voice-assistant --stop --quiet
   - (The script will show its own "Done" notification)

4. Else Actions (if process is not running):
   - Display Text Briefly: "📋 Listening for command..."
   - Execute Shell Script: voice-assistant --device-index 1 --quiet &
   - Select "Display results in a notification"

This approach uses standard Unix background processes (&) instead of Python daemons!
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import pyperclip
import typer
from rich.console import Console

import agent_cli.agents._cli_options as opts
from agent_cli import asr, process_manager, tts
from agent_cli.audio import (
    input_device,
    list_input_devices,
    list_output_devices,
    output_device,
    pyaudio_context,
)
from agent_cli.cli import app, setup_logging
from agent_cli.llm import process_and_update_clipboard
from agent_cli.utils import (
    _print,
    get_clipboard_text,
    print_device_index,
    print_input_panel,
    print_status_message,
    signal_handling_context,
)

if TYPE_CHECKING:
    import pyaudio

LOGGER = logging.getLogger()

# LLM Prompts
SYSTEM_PROMPT = """\
You are a versatile AI text assistant. Your purpose is to either **modify** a given text or **answer questions** about it, based on a specific instruction.

- If the instruction is a **command to edit** the text (e.g., "make this more formal," "add emojis," "correct spelling"), you must return ONLY the full, modified text.
- If the instruction is a **question about** the text (e.g., "summarize this," "what are the key points?," "translate to French"), you must return ONLY the answer.

In all cases, you must follow these strict rules:
- Do not provide any explanations, apologies, or introductory phrases like "Here is the result:".
- Do not wrap your output in markdown or code blocks.
- Your output should be the direct result of the instruction: either the edited text or the answer to the question.
"""

AGENT_INSTRUCTIONS = """\
You will be given a block of text enclosed in <original-text> tags, and an instruction enclosed in <instruction> tags.
Analyze the instruction to determine if it's a command to edit the text or a question about it.

- If it is an editing command, apply the changes to the original text and return the complete, modified version.
- If it is a question, formulate an answer based on the original text.

Return ONLY the resulting text (either the edit or the answer), with no extra formatting or commentary.
"""


# --- Main Application Logic ---


def _setup_devices(
    p: pyaudio.PyAudio,
    console: Console | None,
    device_name: str | None,
    device_index: int | None,
    *,
    enable_tts: bool,
    output_device_name: str | None,
    output_device_index: int | None,
) -> tuple[int | None, str | None, int | None, str | None]:
    """Setup input and output audio devices."""
    device_index, device_name = input_device(p, device_name, device_index)

    # Get output device info for TTS if enabled
    tts_output_device_index = output_device_index
    tts_output_device_name = output_device_name
    if enable_tts and (output_device_name or output_device_index):
        tts_output_device_index, tts_output_device_name = output_device(
            p,
            output_device_name,
            output_device_index,
        )

    # Print device info
    print_device_index(console, device_index, device_name)
    if enable_tts and tts_output_device_index is not None and console:
        msg = f"🔊 TTS output device [bold yellow]{tts_output_device_index}[/bold yellow] ([italic]{tts_output_device_name}[/italic])"
        print_status_message(console, msg)

    return device_index, device_name, tts_output_device_index, tts_output_device_name


async def _save_tts_audio(
    audio_data: bytes,
    save_file: str,
    console: Console | None,
    logger: logging.Logger,
) -> None:
    """Save TTS audio data to file."""
    try:
        save_path = Path(save_file)
        await asyncio.to_thread(save_path.write_bytes, audio_data)
        if console:
            print_status_message(console, f"💾 TTS audio saved to {save_file}")
        logger.info("TTS audio saved to %s", save_file)
    except (OSError, PermissionError) as e:
        logger.exception("Failed to save TTS audio")
        if console:
            print_status_message(console, f"❌ Failed to save TTS audio: {e}", style="red")


async def _handle_tts_response(
    *,
    enable_tts: bool,
    clipboard: bool,
    tts_server_ip: str,
    tts_server_port: int,
    voice_name: str | None,
    tts_language: str | None,
    speaker: str | None,
    save_file: str | None,
    tts_output_device_index: int | None,
    console: Console | None,
    logger: logging.Logger,
) -> None:
    """Handle TTS response generation and playback."""
    if not (enable_tts and clipboard):
        return

    try:
        response_text = pyperclip.paste()
        if response_text and response_text.strip():
            print_status_message(console, "🔊 Speaking response...", style="blue")
            audio_data = await tts.speak_text(
                text=response_text,
                tts_server_ip=tts_server_ip,
                tts_server_port=tts_server_port,
                logger=logger,
                voice_name=voice_name,
                language=tts_language,
                speaker=speaker,
                console=console,
                play_audio_flag=not save_file,  # Don't play if saving to file
                output_device_index=tts_output_device_index,
            )

            # Save TTS audio to file if requested
            if save_file and audio_data:
                await _save_tts_audio(audio_data, save_file, console, logger)

    except (OSError, ConnectionError, TimeoutError) as e:
        logger.warning("Failed to speak response: %s", e)
        if console:
            print_status_message(console, f"⚠️ TTS failed: {e}", style="yellow")


async def async_main(
    *,
    quiet: bool,
    device_index: int | None,
    device_name: str | None,
    list_devices: bool,
    asr_server_ip: str,
    asr_server_port: int,
    model: str,
    ollama_host: str,
    clipboard: bool,
    # TTS parameters
    enable_tts: bool,
    tts_server_ip: str,
    tts_server_port: int,
    voice_name: str | None,
    tts_language: str | None,
    speaker: str | None,
    output_device_index: int | None,
    output_device_name: str | None,
    list_output_devices_flag: bool,
    save_file: str | None,
) -> None:
    """Main async function, consumes parsed arguments."""
    console = Console() if not quiet else None

    with pyaudio_context() as p:
        if list_devices:
            list_input_devices(p, console)
            return

        if list_output_devices_flag:
            list_output_devices(p, console)
            return

        device_index, device_name, tts_output_device_index, tts_output_device_name = _setup_devices(
            p,
            console,
            device_name,
            device_index,
            enable_tts=enable_tts,
            output_device_name=output_device_name,
            output_device_index=output_device_index,
        )

        original_text = get_clipboard_text(console)
        if not original_text:
            return

        print_input_panel(console, original_text, title="📝 Text to Process")

        with signal_handling_context(console, LOGGER) as stop_event:
            # Define callbacks for voice assistant specific formatting
            def chunk_callback(chunk_text: str) -> None:
                """Handle transcript chunks as they arrive."""
                _print(console, chunk_text, end="")

            def final_callback(transcript_text: str) -> None:
                """Format the final instruction result."""
                print_status_message(
                    console,
                    f"\n🎯 Instruction: {transcript_text}",
                    style="bold green",
                )

            instruction = await asr.transcribe_audio(
                asr_server_ip=asr_server_ip,
                asr_server_port=asr_server_port,
                device_index=device_index,
                logger=LOGGER,
                p=p,
                stop_event=stop_event,
                console=console,
                listening_message="Listening for your command...",
                chunk_callback=chunk_callback,
                final_callback=final_callback,
            )

            if not instruction or not instruction.strip():
                print_status_message(
                    console,
                    "No instruction was transcribed. Exiting.",
                    style="yellow",
                )
                return

            await process_and_update_clipboard(
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=AGENT_INSTRUCTIONS,
                model=model,
                ollama_host=ollama_host,
                logger=LOGGER,
                console=console,
                original_text=original_text,
                instruction=instruction,
                clipboard=clipboard,
            )

            # Handle TTS response
            await _handle_tts_response(
                enable_tts=enable_tts,
                clipboard=clipboard,
                tts_server_ip=tts_server_ip,
                tts_server_port=tts_server_port,
                voice_name=voice_name,
                tts_language=tts_language,
                speaker=speaker,
                save_file=save_file,
                tts_output_device_index=tts_output_device_index,
                console=console,
                logger=LOGGER,
            )


@app.command("voice-assistant")
def voice_assistant(
    device_index: int | None = opts.DEVICE_INDEX,
    device_name: str | None = opts.DEVICE_NAME,
    *,
    # ASR
    list_devices: bool = opts.LIST_DEVICES,
    asr_server_ip: str = opts.ASR_SERVER_IP,
    asr_server_port: int = opts.ASR_SERVER_PORT,
    # LLM
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    # Process control
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    # General
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    # TTS parameters
    enable_tts: bool = opts.ENABLE_TTS,
    tts_server_ip: str = opts.TTS_SERVER_IP,
    tts_server_port: int = opts.TTS_SERVER_PORT,
    voice_name: str | None = opts.VOICE_NAME,
    tts_language: str | None = opts.TTS_LANGUAGE,
    speaker: str | None = opts.SPEAKER,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    list_output_devices_flag: bool = opts.LIST_OUTPUT_DEVICES,
    # Output
    save_file: str | None = typer.Option(
        None,
        "--save-file",
        help="Save TTS response audio to WAV file.",
    ),
) -> None:
    """Interact with clipboard text via a voice command using Wyoming and an Ollama LLM.

    Usage:
    - Run in foreground: agent-cli voice-assistant --device-index 1
    - Run in background: agent-cli voice-assistant --device-index 1 &
    - Check status: agent-cli voice-assistant --status
    - Stop background process: agent-cli voice-assistant --stop
    - List output devices: agent-cli voice-assistant --list-output-devices
    - Save TTS to file: agent-cli voice-assistant --tts --save-file response.wav
    """
    setup_logging(log_level, log_file, quiet=quiet)
    console = Console() if not quiet else None
    process_name = "voice-assistant"

    if stop:
        if process_manager.kill_process(process_name):
            print_status_message(console, "✅ Voice assistant stopped.")
        else:
            print_status_message(console, "⚠️  No voice assistant is running.", style="yellow")
        return

    if status:
        if process_manager.is_process_running(process_name):
            pid = process_manager.read_pid_file(process_name)
            print_status_message(console, f"✅ Voice assistant is running (PID: {pid}).")
        else:
            print_status_message(console, "⚠️  Voice assistant is not running.", style="yellow")
        return

    # Use context manager for PID file management
    with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
        asyncio.run(
            async_main(
                quiet=quiet,
                device_index=device_index,
                device_name=device_name,
                list_devices=list_devices,
                asr_server_ip=asr_server_ip,
                asr_server_port=asr_server_port,
                model=model,
                ollama_host=ollama_host,
                clipboard=clipboard,
                # TTS parameters
                enable_tts=enable_tts,
                tts_server_ip=tts_server_ip,
                tts_server_port=tts_server_port,
                voice_name=voice_name,
                tts_language=tts_language,
                speaker=speaker,
                output_device_index=output_device_index,
                output_device_name=output_device_name,
                list_output_devices_flag=list_output_devices_flag,
                save_file=save_file,
            ),
        )
