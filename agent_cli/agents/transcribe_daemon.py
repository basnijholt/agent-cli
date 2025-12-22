"""Continuous transcription daemon with voice activity detection."""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import signal
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import typer

from agent_cli import config, constants, opts
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import open_audio_stream, setup_devices, setup_input_stream
from agent_cli.core.audio_format import check_ffmpeg_available, save_audio_as_mp3
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_with_style,
    setup_logging,
)
from agent_cli.core.vad import VoiceActivityDetector
from agent_cli.services.asr import create_recorded_audio_transcriber
from agent_cli.services.llm import process_and_update_clipboard

LOGGER = logging.getLogger()

# Reuse prompts from the transcribe module
SYSTEM_PROMPT = """
CRITICAL: You must respond with ONLY the cleaned transcription text. Do NOT add any prefixes, explanations, or commentary whatsoever.

WRONG responses (DO NOT DO THIS):
- "Sure. Here's the cleaned-up text: [text]"
- "Here is the cleaned text: [text]"
- "Certainly. Here's the cleaned-up text: [text]"
- Any text wrapped in quotes like "[text]"

CORRECT response: Just the cleaned text directly, nothing else.

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
- Do not wrap your output in markdown or code blocks
"""

AGENT_INSTRUCTIONS = """
REMINDER: Respond with ONLY the cleaned text. No prefixes like "Here's the cleaned text:" or quotes around your response.

You will be given a block of raw transcribed text enclosed in <original-text> tags, and a cleanup instruction enclosed in <instruction> tags.

Your job is to process the transcribed text according to the instruction, which will typically involve:
- Correcting speech recognition errors
- Adding proper punctuation and capitalization
- Removing obvious filler words and false starts
- Improving readability while preserving meaning

Your response must be JUST the cleaned text - nothing before it, nothing after it, no quotes around it.
"""

INSTRUCTION = """
Please clean up this transcribed text by correcting any speech recognition errors, adding appropriate punctuation and capitalization, removing obvious filler words or false starts, and improving overall readability while preserving the original meaning and intent of the speaker.
"""


def _get_audio_dir() -> Path:
    """Get the default directory for storing audio files."""
    return Path.home() / ".config" / "agent-cli" / "audio"


def _get_log_file() -> Path:
    """Get the default transcription log file path."""
    return Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"


def _generate_audio_path(audio_dir: Path, timestamp: datetime) -> Path:
    """Generate a path for an audio file based on timestamp.

    Creates a directory structure: audio_dir/YYYY/MM/DD/HHMMSS_mmm.mp3
    """
    date_dir = audio_dir / timestamp.strftime("%Y/%m/%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    filename = timestamp.strftime("%H%M%S") + f"_{timestamp.microsecond // 1000:03d}.mp3"
    return date_dir / filename


def _log_segment(
    log_file: Path,
    *,
    timestamp: datetime,
    role: str,
    raw_output: str,
    processed_output: str | None,
    audio_file: Path | None,
    duration_seconds: float,
    model_info: str | None = None,
) -> None:
    """Append a transcription segment to the JSON Lines log file."""
    log_entry = {
        "timestamp": timestamp.isoformat(),
        "hostname": platform.node(),
        "role": role,
        "model": model_info,
        "raw_output": raw_output,
        "processed_output": processed_output,
        "audio_file": str(audio_file) if audio_file else None,
        "duration_seconds": round(duration_seconds, 2),
    }

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


async def _process_segment(  # noqa: PLR0912
    segment: bytes,
    *,
    timestamp: datetime,
    role: str,
    vad: VoiceActivityDetector,
    provider_cfg: config.ProviderSelection,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    llm_enabled: bool,
    save_audio: bool,
    audio_dir: Path,
    log_file: Path,
    quiet: bool,
) -> None:
    """Process a single speech segment: transcribe, optionally process with LLM, and log."""
    duration_seconds = vad.get_segment_duration_seconds(segment)

    # Skip very short segments
    if duration_seconds < 0.3:  # noqa: PLR2004
        LOGGER.debug("Skipping very short segment: %.2fs", duration_seconds)
        return

    # Save audio as MP3 if requested
    audio_path: Path | None = None
    if save_audio:
        try:
            audio_path = _generate_audio_path(audio_dir, timestamp)
            save_audio_as_mp3(segment, audio_path)
            LOGGER.debug("Saved audio to %s", audio_path)
        except RuntimeError:
            LOGGER.exception("Failed to save audio as MP3")
            audio_path = None

    # Transcribe the segment
    transcriber = create_recorded_audio_transcriber(provider_cfg)

    try:
        if provider_cfg.asr_provider == "openai":
            transcript = await transcriber(
                segment,
                openai_asr_cfg,
                LOGGER,
                quiet=quiet,
            )
        else:  # Wyoming expects keyword arguments
            transcript = await transcriber(
                audio_data=segment,
                wyoming_asr_cfg=wyoming_asr_cfg,
                logger=LOGGER,
                quiet=quiet,
            )
    except Exception:
        LOGGER.exception("Transcription failed")
        return

    if not transcript or not transcript.strip():
        LOGGER.debug("Empty transcript, skipping")
        if not quiet:
            # Clear status line and show listening
            console.print("[green]👂 Listening...[/green]" + " " * 20, end="\r")
        return

    if not quiet:
        # Clear status line and print transcript
        console.print(" " * 50, end="\r")  # Clear line
        console.print(
            f"[dim]{timestamp.strftime('%H:%M:%S')}[/dim] [cyan]{role}[/cyan]: {transcript}",
        )

    # Process with LLM if enabled
    processed_transcript: str | None = None
    model_info: str | None = None

    if llm_enabled:
        try:
            # Determine model info for logging
            if provider_cfg.llm_provider == "ollama":
                model_info = f"{provider_cfg.llm_provider}:{ollama_cfg.llm_ollama_model}"
            elif provider_cfg.llm_provider == "openai":
                model_info = f"{provider_cfg.llm_provider}:{openai_llm_cfg.llm_openai_model}"
            elif provider_cfg.llm_provider == "gemini":
                model_info = f"{provider_cfg.llm_provider}:{gemini_llm_cfg.llm_gemini_model}"

            processed_transcript = await process_and_update_clipboard(
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=AGENT_INSTRUCTIONS,
                provider_cfg=provider_cfg,
                ollama_cfg=ollama_cfg,
                openai_cfg=openai_llm_cfg,
                gemini_cfg=gemini_llm_cfg,
                logger=LOGGER,
                original_text=transcript,
                instruction=INSTRUCTION,
                clipboard=False,  # Don't copy to clipboard in daemon mode
                quiet=True,  # Suppress LLM output, we handle display ourselves
                live=None,
                context=None,
            )

            if not quiet and processed_transcript and processed_transcript != transcript:
                console.print(f"  [dim]→[/dim] [green]{processed_transcript}[/green]")

        except Exception:
            LOGGER.exception("LLM processing failed")

    # Log the segment
    asr_model_info = f"{provider_cfg.asr_provider}"
    if provider_cfg.asr_provider == "openai":
        asr_model_info += f":{openai_asr_cfg.asr_openai_model}"

    _log_segment(
        log_file,
        timestamp=timestamp,
        role=role,
        raw_output=transcript,
        processed_output=processed_transcript,
        audio_file=audio_path,
        duration_seconds=duration_seconds,
        model_info=model_info or asr_model_info,
    )


async def _daemon_loop(  # noqa: C901, PLR0912, PLR0915
    *,
    role: str,
    vad: VoiceActivityDetector,
    input_device_index: int | None,
    provider_cfg: config.ProviderSelection,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    llm_enabled: bool,
    save_audio: bool,
    audio_dir: Path,
    log_file: Path,
    quiet: bool,
) -> None:
    """Main daemon loop: continuously capture audio and process speech segments."""
    stream_config = setup_input_stream(input_device_index)

    # Track background tasks to prevent garbage collection
    background_tasks: set[asyncio.Task[None]] = set()

    def _task_done_callback(task: asyncio.Task[None]) -> None:
        """Remove completed task from tracking set."""
        background_tasks.discard(task)

    if not quiet:
        print_with_style("🎙️ Transcribe daemon started. Listening...", style="green")
        print_with_style(f"   Role: {role}", style="dim")
        print_with_style(f"   Log file: {log_file}", style="dim")
        if save_audio:
            print_with_style(f"   Audio dir: {audio_dir}", style="dim")
        print_with_style("   Press Ctrl+C to stop.", style="dim")
        console.print()

    # Track state for status display
    was_speaking = False
    shutdown_event = asyncio.Event()

    def _cancel_all_tasks() -> None:
        """Cancel all pending background tasks."""
        for task in background_tasks:
            if not task.done():
                task.cancel()

    def _signal_handler() -> None:
        """Handle shutdown signals."""
        shutdown_event.set()

    # Register signal handlers for clean shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    with open_audio_stream(stream_config) as stream:
        try:
            while not shutdown_event.is_set():
                # Read audio chunk with timeout to allow checking shutdown flag
                try:
                    data, _overflow = await asyncio.to_thread(
                        stream.read,
                        constants.AUDIO_CHUNK_SIZE,
                    )
                    chunk = data.tobytes()
                except asyncio.CancelledError:
                    LOGGER.debug("Audio read cancelled")
                    break
                except Exception:
                    LOGGER.exception("Error reading audio stream")
                    await asyncio.sleep(0.1)
                    continue

                # Process through VAD
                is_speaking, segment = vad.process_chunk(chunk)

                # Show status changes
                if not quiet:
                    if is_speaking and not was_speaking:
                        # Speech just started
                        console.print("[red]🔴 Recording...[/red]", end="\r")
                    elif not is_speaking and was_speaking and segment is None:
                        # Still in silence buffer, waiting to see if speech resumes
                        console.print("[yellow]⏸️  Pause detected...[/yellow]", end="\r")

                was_speaking = is_speaking

                if segment:
                    timestamp = datetime.now(UTC)
                    duration = vad.get_segment_duration_seconds(segment)

                    if not quiet:
                        # Clear the status line and show processing message
                        console.print(
                            f"[blue]⏳ Processing {duration:.1f}s segment...[/blue]",
                            end="\r",
                        )

                    LOGGER.debug("Speech segment detected, %.2f seconds", duration)

                    # Process segment in background to not block audio capture
                    task = asyncio.create_task(
                        _process_segment(
                            segment,
                            timestamp=timestamp,
                            role=role,
                            vad=vad,
                            provider_cfg=provider_cfg,
                            wyoming_asr_cfg=wyoming_asr_cfg,
                            openai_asr_cfg=openai_asr_cfg,
                            ollama_cfg=ollama_cfg,
                            openai_llm_cfg=openai_llm_cfg,
                            gemini_llm_cfg=gemini_llm_cfg,
                            llm_enabled=llm_enabled,
                            save_audio=save_audio,
                            audio_dir=audio_dir,
                            log_file=log_file,
                            quiet=quiet,
                        ),
                    )
                    background_tasks.add(task)
                    task.add_done_callback(_task_done_callback)

        except (KeyboardInterrupt, asyncio.CancelledError):
            LOGGER.debug("Shutdown signal received")
        finally:
            # Remove signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                with suppress(ValueError):
                    loop.remove_signal_handler(sig)

            # Abort the stream to unblock any pending reads
            with suppress(Exception):
                stream.abort()

            # Cancel all pending background tasks
            _cancel_all_tasks()
            # Wait briefly for tasks to finish
            if background_tasks:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait(background_tasks, timeout=2.0)


@app.command("transcribe-daemon")
def transcribe_daemon(  # noqa: PLR0912
    *,
    # Daemon-specific options
    role: str = typer.Option(
        "user",
        "--role",
        "-r",
        help="Role name for logging (e.g., 'meeting', 'notes', 'user').",
    ),
    silence_threshold: float = typer.Option(
        1.0,
        "--silence-threshold",
        "-s",
        help="Seconds of silence to end a speech segment.",
    ),
    min_segment: float = typer.Option(
        0.5,
        "--min-segment",
        "-m",
        help="Minimum speech duration in seconds to trigger a segment.",
    ),
    vad_aggressiveness: int = typer.Option(
        2,
        "--vad-aggressiveness",
        help="VAD aggressiveness mode (0-3). Higher = more aggressive filtering.",
    ),
    save_audio: bool = typer.Option(
        True,  # noqa: FBT003
        "--save-audio/--no-save-audio",
        help="Save audio segments as MP3 files.",
    ),
    audio_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--audio-dir",
        help="Directory for MP3 files. Default: ~/.config/agent-cli/audio",
    ),
    transcription_log: Path | None = typer.Option(  # noqa: B008
        None,
        "--transcription-log",
        "-t",
        help="JSON Lines log file path. Default: ~/.config/agent-cli/transcriptions.jsonl",
    ),
    # --- Provider Selection ---
    asr_provider: str = opts.ASR_PROVIDER,
    llm_provider: str = opts.LLM_PROVIDER,
    # --- ASR (Audio) Configuration ---
    input_device_index: int | None = opts.INPUT_DEVICE_INDEX,
    input_device_name: str | None = opts.INPUT_DEVICE_NAME,
    asr_wyoming_ip: str = opts.ASR_WYOMING_IP,
    asr_wyoming_port: int = opts.ASR_WYOMING_PORT,
    asr_openai_model: str = opts.ASR_OPENAI_MODEL,
    asr_openai_base_url: str | None = opts.ASR_OPENAI_BASE_URL,
    asr_openai_prompt: str | None = opts.ASR_OPENAI_PROMPT,
    # --- LLM Configuration ---
    llm_ollama_model: str = opts.LLM_OLLAMA_MODEL,
    llm_ollama_host: str = opts.LLM_OLLAMA_HOST,
    llm_openai_model: str = opts.LLM_OPENAI_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    llm_gemini_model: str = opts.LLM_GEMINI_MODEL,
    gemini_api_key: str | None = opts.GEMINI_API_KEY,
    llm: bool = opts.LLM,
    # --- Process Management ---
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    # --- General Options ---
    log_level: str = opts.LOG_LEVEL,
    log_file_logging: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Run a continuous transcription daemon with voice activity detection.

    This command runs indefinitely, capturing audio from your microphone,
    detecting speech segments using webrtcvad, transcribing them, and
    logging results with timestamps.

    Examples:
        # Basic daemon
        agent-cli transcribe-daemon

        # With role and custom silence threshold
        agent-cli transcribe-daemon --role meeting --silence-threshold 1.5

        # With LLM cleanup
        agent-cli transcribe-daemon --llm --role notes

        # Custom log file and audio directory
        agent-cli transcribe-daemon --transcription-log ~/meeting.jsonl --audio-dir ~/audio

    """
    if print_args:
        print_command_line_args(locals())
    setup_logging(log_level, log_file_logging, quiet=quiet)

    process_name = "transcribe-daemon"

    # Handle stop/status commands
    if stop:
        if process.kill_process(process_name):
            if not quiet:
                print_with_style(f"✅ Stopped {process_name}", style="green")
        elif not quiet:
            print_with_style(f"⚠️ {process_name} is not running", style="yellow")
        return

    if status:
        if process.is_process_running(process_name):
            if not quiet:
                print_with_style(f"✅ {process_name} is running", style="green")
        elif not quiet:
            print_with_style(f"⚠️ {process_name} is not running", style="yellow")
        return

    # Validate VAD aggressiveness
    if vad_aggressiveness < 0 or vad_aggressiveness > 3:  # noqa: PLR2004
        print_with_style("❌ VAD aggressiveness must be 0-3", style="red")
        raise typer.Exit(1)

    # Check FFmpeg availability if saving audio
    if save_audio and not check_ffmpeg_available():
        print_with_style(
            "⚠️ FFmpeg not found. Audio saving disabled. Install FFmpeg for MP3 support.",
            style="yellow",
        )
        save_audio = False

    # Set default paths
    audio_dir_path = audio_dir.expanduser() if audio_dir else _get_audio_dir()
    log_file_path = transcription_log.expanduser() if transcription_log else _get_log_file()

    # Create config objects
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file_logging,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,
    )
    provider_cfg = config.ProviderSelection(
        asr_provider=asr_provider,
        llm_provider=llm_provider,
        tts_provider="wyoming",  # Not used
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
        openai_base_url=asr_openai_base_url,
        asr_openai_prompt=asr_openai_prompt,
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model=llm_ollama_model,
        llm_ollama_host=llm_ollama_host,
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=llm_openai_model,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model=llm_gemini_model,
        gemini_api_key=gemini_api_key,
    )

    # Setup audio device
    device_info = setup_devices(general_cfg, audio_in_cfg, None)
    if device_info is None:
        return
    resolved_input_device_index, _, _ = device_info

    # Create VAD instance
    vad = VoiceActivityDetector(
        aggressiveness=vad_aggressiveness,
        silence_threshold_ms=int(silence_threshold * 1000),
        min_speech_duration_ms=int(min_segment * 1000),
    )

    # Run the daemon
    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        asyncio.run(
            _daemon_loop(
                role=role,
                vad=vad,
                input_device_index=resolved_input_device_index,
                provider_cfg=provider_cfg,
                wyoming_asr_cfg=wyoming_asr_cfg,
                openai_asr_cfg=openai_asr_cfg,
                ollama_cfg=ollama_cfg,
                openai_llm_cfg=openai_llm_cfg,
                gemini_llm_cfg=gemini_llm_cfg,
                llm_enabled=llm,
                save_audio=save_audio,
                audio_dir=audio_dir_path,
                log_file=log_file_path,
                quiet=quiet,
            ),
        )

    if not quiet:
        console.print()
        print_with_style("👋 Transcribe daemon stopped.", style="yellow")
