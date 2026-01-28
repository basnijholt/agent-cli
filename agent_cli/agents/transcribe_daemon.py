"""Continuous transcription daemon with voice activity detection."""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import signal
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from agent_cli import config, constants, opts
from agent_cli.agents.transcribe import (
    AGENT_INSTRUCTIONS,
    INSTRUCTION,
    SYSTEM_PROMPT,
)
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import open_audio_stream, setup_devices, setup_input_stream
from agent_cli.core.audio_format import check_ffmpeg_available, save_audio_as_mp3
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_with_style,
    setup_logging,
)
from agent_cli.services.asr import create_recorded_audio_transcriber
from agent_cli.services.llm import process_and_update_clipboard

if TYPE_CHECKING:
    from agent_cli.core.vad import VoiceActivityDetector

LOGGER = logging.getLogger()

_DEFAULT_AUDIO_DIR = Path.home() / ".config" / "agent-cli" / "audio"
_DEFAULT_LOG_FILE = Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"
_MIN_SEGMENT_DURATION_SECONDS = 0.3


@dataclass
class DaemonConfig:
    """Bundle of all daemon configuration."""

    role: str
    vad: VoiceActivityDetector
    input_device_index: int | None
    provider: config.ProviderSelection
    wyoming_asr: config.WyomingASR
    openai_asr: config.OpenAIASR
    gemini_asr: config.GeminiASR
    ollama: config.Ollama
    openai_llm: config.OpenAILLM
    gemini_llm: config.GeminiLLM
    llm_enabled: bool
    save_audio: bool
    audio_dir: Path
    log_file: Path
    quiet: bool
    clipboard: bool


def _generate_audio_path(audio_dir: Path, timestamp: datetime) -> Path:
    """Generate a path for an audio file based on timestamp."""
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
    """Append a transcription segment to the log file."""
    entry = {
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
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def _process_segment(  # noqa: PLR0912
    cfg: DaemonConfig,
    segment: bytes,
    timestamp: datetime,
) -> None:
    """Process a speech segment: transcribe, optionally LLM-clean, and log."""
    duration = cfg.vad.get_segment_duration_seconds(segment)
    if duration < _MIN_SEGMENT_DURATION_SECONDS:
        LOGGER.debug("Skipping very short segment: %.2fs", duration)
        return

    # Save audio as MP3 if requested (run in thread to avoid blocking event loop)
    audio_path: Path | None = None
    if cfg.save_audio:
        try:
            audio_path = _generate_audio_path(cfg.audio_dir, timestamp)
            await asyncio.to_thread(save_audio_as_mp3, segment, audio_path)
            LOGGER.debug("Saved audio to %s", audio_path)
        except RuntimeError:
            LOGGER.exception("Failed to save audio as MP3")

    # Transcribe
    transcriber = create_recorded_audio_transcriber(cfg.provider)
    if cfg.provider.asr_provider == "openai":
        transcript = await transcriber(segment, cfg.openai_asr, LOGGER, quiet=cfg.quiet)
    elif cfg.provider.asr_provider == "gemini":
        transcript = await transcriber(segment, cfg.gemini_asr, LOGGER, quiet=cfg.quiet)
    elif cfg.provider.asr_provider == "wyoming":
        transcript = await transcriber(
            audio_data=segment,
            wyoming_asr_cfg=cfg.wyoming_asr,
            logger=LOGGER,
            quiet=cfg.quiet,
        )
    else:
        msg = f"Unsupported ASR provider: {cfg.provider.asr_provider}"
        raise NotImplementedError(msg)

    if not transcript or not transcript.strip():
        LOGGER.debug("Empty transcript, skipping")
        if not cfg.quiet:
            console.print("[green]👂 Listening...[/green]" + " " * 20, end="\r")
        return

    if not cfg.quiet:
        console.print(" " * 50, end="\r")
        console.print(
            f"[dim]{timestamp.strftime('%H:%M:%S')}[/dim] [cyan]{cfg.role}[/cyan]: {transcript}",
        )
        console.file.flush()

    # LLM cleanup if enabled
    processed: str | None = None
    model_info: str | None = None

    if cfg.llm_enabled:
        models = {
            "ollama": cfg.ollama.llm_ollama_model,
            "openai": cfg.openai_llm.llm_openai_model,
            "gemini": cfg.gemini_llm.llm_gemini_model,
        }
        model_info = f"{cfg.provider.llm_provider}:{models.get(cfg.provider.llm_provider, '')}"

        processed = await process_and_update_clipboard(
            system_prompt=SYSTEM_PROMPT,
            agent_instructions=AGENT_INSTRUCTIONS,
            provider_cfg=cfg.provider,
            ollama_cfg=cfg.ollama,
            openai_cfg=cfg.openai_llm,
            gemini_cfg=cfg.gemini_llm,
            logger=LOGGER,
            original_text=transcript,
            instruction=INSTRUCTION,
            clipboard=False,
            quiet=True,
            live=None,
            context=None,
        )

        if not cfg.quiet and processed and processed != transcript:
            console.print(f"  [dim]→[/dim] [green]{processed}[/green]")

    # Copy to clipboard if enabled
    if cfg.clipboard:
        import pyperclip  # noqa: PLC0415

        text_to_copy = processed if processed else transcript
        pyperclip.copy(text_to_copy)

    # Log
    asr_model: str = cfg.provider.asr_provider
    if cfg.provider.asr_provider == "openai":
        asr_model += f":{cfg.openai_asr.asr_openai_model}"

    _log_segment(
        cfg.log_file,
        timestamp=timestamp,
        role=cfg.role,
        raw_output=transcript,
        processed_output=processed,
        audio_file=audio_path,
        duration_seconds=duration,
        model_info=model_info or asr_model,
    )

    if not cfg.quiet:
        console.print("[green]👂 Listening...[/green]" + " " * 20, end="\r")


async def _daemon_loop(cfg: DaemonConfig) -> None:  # noqa: PLR0912, PLR0915
    """Main daemon loop: continuously capture audio and process speech segments."""
    stream_config = setup_input_stream(cfg.input_device_index)
    background_tasks: set[asyncio.Task[None]] = set()

    if not cfg.quiet:
        print_with_style("🎙️ Transcribe daemon started. Listening...", style="green")
        print_with_style(f"   Role: {cfg.role}", style="dim")
        print_with_style(f"   Log file: {cfg.log_file}", style="dim")
        if cfg.save_audio:
            print_with_style(f"   Audio dir: {cfg.audio_dir}", style="dim")
        print_with_style("   Press Ctrl+C to stop.", style="dim")
        console.print()

    was_speaking = False
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    with open_audio_stream(stream_config) as stream:
        try:
            while not shutdown_event.is_set():
                try:
                    data, _ = await asyncio.to_thread(stream.read, constants.AUDIO_CHUNK_SIZE)
                    chunk = data.tobytes()
                except asyncio.CancelledError:
                    break
                except Exception:
                    LOGGER.exception("Error reading audio stream")
                    await asyncio.sleep(0.1)
                    continue

                is_speaking, segment = cfg.vad.process_chunk(chunk)

                if not cfg.quiet:
                    if is_speaking and not was_speaking:
                        console.print("[red]🔴 Recording...[/red]", end="\r")
                    elif not is_speaking and was_speaking and segment is None:
                        console.print("[yellow]⏸️  Pause detected...[/yellow]", end="\r")

                was_speaking = is_speaking

                if segment:
                    timestamp = datetime.now(UTC).astimezone()
                    duration = cfg.vad.get_segment_duration_seconds(segment)

                    if not cfg.quiet:
                        console.print(
                            f"[blue]⏳ Processing {duration:.1f}s segment...[/blue]",
                            end="\r",
                        )

                    LOGGER.debug("Speech segment detected, %.2f seconds", duration)

                    task = asyncio.create_task(_process_segment(cfg, segment, timestamp))
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)

        except (KeyboardInterrupt, asyncio.CancelledError):
            LOGGER.debug("Shutdown signal received")
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                with suppress(ValueError):
                    loop.remove_signal_handler(sig)
            with suppress(Exception):
                stream.abort()
            for task in background_tasks:
                if not task.done():
                    task.cancel()
            if background_tasks:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait(background_tasks, timeout=2.0)


@app.command("transcribe-daemon", rich_help_panel="Voice Commands")
@requires_extras("audio", "vad", "llm")
def transcribe_daemon(  # noqa: PLR0912
    *,
    # Daemon-specific options
    role: str = typer.Option(
        "user",
        "--role",
        "-r",
        help="Label for log entries. Use to distinguish speakers or contexts in logs.",
    ),
    silence_threshold: float = typer.Option(
        1.0,
        "--silence-threshold",
        "-s",
        help="Seconds of silence after speech to finalize a segment. Increase for slower speakers.",
    ),
    min_segment: float = typer.Option(
        0.25,
        "--min-segment",
        "-m",
        help="Minimum seconds of speech required before a segment is processed. Filters brief sounds.",
    ),
    vad_threshold: float = typer.Option(
        0.3,
        "--vad-threshold",
        help="Silero VAD confidence threshold (0.0-1.0). Higher values require clearer speech; lower values are more sensitive to quiet/distant voices.",
    ),
    save_audio: bool = typer.Option(
        True,  # noqa: FBT003
        "--save-audio/--no-save-audio",
        help="Save each speech segment as MP3. Requires `ffmpeg` to be installed.",
    ),
    audio_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--audio-dir",
        help="Base directory for MP3 files. Files are organized by date: `YYYY/MM/DD/HHMMSS_mmm.mp3`. Default: `~/.config/agent-cli/audio`.",
    ),
    transcription_log: Path | None = typer.Option(  # noqa: B008
        None,
        "--transcription-log",
        "-t",
        help="JSONL file for transcript logging (one JSON object per line with timestamp, role, raw/processed text, audio path). Default: `~/.config/agent-cli/transcriptions.jsonl`.",
    ),
    clipboard: bool = typer.Option(
        False,  # noqa: FBT003
        "--clipboard/--no-clipboard",
        help="Copy each completed transcription to clipboard (overwrites previous). Useful with `--llm` to get cleaned text.",
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
    asr_gemini_model: str = opts.ASR_GEMINI_MODEL,
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
    log_level: opts.LogLevel = opts.LOG_LEVEL,
    log_file_logging: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Continuous transcription daemon using Silero VAD for speech detection.

    Unlike `transcribe` (single recording session), this daemon runs indefinitely
    and automatically detects speech segments using Voice Activity Detection (VAD).
    Each detected segment is transcribed and logged with timestamps.

    **How it works:**

    1. Listens continuously to microphone input
    2. Silero VAD detects when you start/stop speaking
    3. After `--silence-threshold` seconds of silence, the segment is finalized
    4. Segment is transcribed (and optionally cleaned by LLM with `--llm`)
    5. Results are appended to the JSONL log file
    6. Audio is saved as MP3 if `--save-audio` is enabled (requires `ffmpeg`)

    **Use cases:** Meeting transcription, note-taking, voice journaling, accessibility.

    **Examples:**

        agent-cli transcribe-daemon
        agent-cli transcribe-daemon --role meeting --silence-threshold 1.5
        agent-cli transcribe-daemon --llm --clipboard --role notes
        agent-cli transcribe-daemon --transcription-log ~/meeting.jsonl --no-save-audio
        agent-cli transcribe-daemon --asr-provider openai --llm-provider gemini --llm

    **Tips:**

    - Use `--role` to tag entries (e.g., `speaker1`, `meeting`, `personal`)
    - Adjust `--vad-threshold` if detection is too sensitive (increase) or missing speech (decrease)
    - Use `--stop` to cleanly terminate a running daemon
    - With `--llm`, transcripts are cleaned up (punctuation, filler words removed)
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

    # Validate VAD threshold
    if vad_threshold < 0.0 or vad_threshold > 1.0:
        print_with_style("❌ VAD threshold must be 0.0-1.0", style="red")
        raise typer.Exit(1)

    # Check FFmpeg availability if saving audio
    if save_audio and not check_ffmpeg_available():
        print_with_style(
            "⚠️ FFmpeg not found. Audio saving disabled. Install FFmpeg for MP3 support.",
            style="yellow",
        )
        save_audio = False

    # Setup audio device
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file_logging,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,
    )
    audio_in_cfg = config.AudioInput(
        input_device_index=input_device_index,
        input_device_name=input_device_name,
    )
    device_info = setup_devices(general_cfg, audio_in_cfg, None)
    if device_info is None:
        return
    resolved_input_device_index, _, _ = device_info

    # Import VAD here to avoid loading torch/numpy at module import time
    from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415

    # Create daemon config
    cfg = DaemonConfig(
        role=role,
        vad=VoiceActivityDetector(
            threshold=vad_threshold,
            silence_threshold_ms=int(silence_threshold * 1000),
            min_speech_duration_ms=int(min_segment * 1000),
        ),
        input_device_index=resolved_input_device_index,
        provider=config.ProviderSelection(
            asr_provider=asr_provider,
            llm_provider=llm_provider,
            tts_provider="wyoming",
        ),
        wyoming_asr=config.WyomingASR(
            asr_wyoming_ip=asr_wyoming_ip,
            asr_wyoming_port=asr_wyoming_port,
        ),
        openai_asr=config.OpenAIASR(
            asr_openai_model=asr_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=asr_openai_base_url or openai_base_url,
            asr_openai_prompt=asr_openai_prompt,
        ),
        gemini_asr=config.GeminiASR(
            asr_gemini_model=asr_gemini_model,
            gemini_api_key=gemini_api_key,
        ),
        ollama=config.Ollama(llm_ollama_model=llm_ollama_model, llm_ollama_host=llm_ollama_host),
        openai_llm=config.OpenAILLM(
            llm_openai_model=llm_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
        ),
        gemini_llm=config.GeminiLLM(
            llm_gemini_model=llm_gemini_model,
            gemini_api_key=gemini_api_key,
        ),
        llm_enabled=llm,
        save_audio=save_audio,
        audio_dir=audio_dir.expanduser() if audio_dir else _DEFAULT_AUDIO_DIR,
        log_file=transcription_log.expanduser() if transcription_log else _DEFAULT_LOG_FILE,
        quiet=quiet,
        clipboard=clipboard,
    )

    # Run the daemon
    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        asyncio.run(_daemon_loop(cfg))

    if not quiet:
        console.print()
        print_with_style("👋 Transcribe daemon stopped.", style="yellow")
