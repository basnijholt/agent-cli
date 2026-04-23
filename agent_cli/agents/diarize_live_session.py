"""Retroactively diarize `transcribe-live` sessions from saved audio chunks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import typer

from agent_cli import config as agent_config
from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.alignment import AlignedWord, align
from agent_cli.core.deps import requires_extras
from agent_cli.core.diarization import (
    DiarizedSegment,
    SpeakerDiarizer,
    align_words_to_speakers,
    format_diarized_output,
)
from agent_cli.core.utils import print_command_line_args, print_with_style

DEFAULT_TRANSCRIPTION_LOG = Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"
DEFAULT_OUTPUT_DIR = Path.home() / ".cache" / "agent-cli" / "live-diarization"
TRANSCRIPTION_LOG_OPTION: Path = typer.Option(
    DEFAULT_TRANSCRIPTION_LOG,
    "--transcription-log",
    help="Path to the transcribe-live JSONL log file.",
)
OUTPUT_DIR_OPTION: Path = typer.Option(
    DEFAULT_OUTPUT_DIR,
    "--output-dir",
    help="Directory where the combined audio and diarized transcript will be saved.",
)
ALIGN_WORDS_OPTION: bool = typer.Option(
    False,  # noqa: FBT003
    "--align-words/--no-align-words",
    help=(
        "Enable word-level alignment when re-transcribing combined audio. "
        "Logged-transcript mode already uses word-level alignment by default."
    ),
    rich_help_panel="Diarization",
)
PREPARE_ONLY_OPTION: bool = typer.Option(
    False,  # noqa: FBT003
    "--prepare-only",
    help="Only create the combined audio file and metadata without running diarization.",
)
RETRANSCRIBE_OPTION: bool = typer.Option(
    False,  # noqa: FBT003
    "--retranscribe",
    help="Re-run ASR on the combined audio instead of using the logged transcribe-live text.",
)


@dataclass(frozen=True)
class LiveSegment:
    """A saved `transcribe-live` segment."""

    timestamp: datetime
    audio_file: Path
    duration_seconds: float
    raw_output: str | None = None


def parse_clock_time(value: str) -> time:
    """Parse HH:MM or HH:MM:SS."""
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        msg = f"Invalid time value: {value!r}. Use HH:MM or HH:MM:SS."
        raise argparse.ArgumentTypeError(msg) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a single WAV from transcribe-live MP3 chunks in a time window and "
            "diarize the resulting session."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now().astimezone().date(),
        help="Date of the live session in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--start",
        type=parse_clock_time,
        required=True,
        help="Start time of the session in HH:MM or HH:MM:SS.",
    )
    parser.add_argument(
        "--end",
        type=parse_clock_time,
        required=True,
        help="End time of the session in HH:MM or HH:MM:SS.",
    )
    parser.add_argument(
        "--transcription-log",
        type=Path,
        default=DEFAULT_TRANSCRIPTION_LOG,
        help="Path to the transcribe-live JSONL log file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the combined audio and diarized transcript will be saved.",
    )
    parser.add_argument(
        "--diarize-format",
        choices=("inline", "json"),
        default="inline",
        help="Speaker diarization output format.",
    )
    parser.add_argument(
        "--speakers",
        type=int,
        default=None,
        help="Known number of speakers. Sets both --min-speakers and --max-speakers.",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=None,
        help="Minimum speaker count hint for diarization.",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=None,
        help="Maximum speaker count hint for diarization.",
    )
    parser.add_argument(
        "--align-words",
        action="store_true",
        help=(
            "Enable word-level alignment when re-transcribing combined audio. "
            "Logged-transcript mode already uses word-level alignment by default."
        ),
    )
    parser.add_argument(
        "--align-language",
        default="en",
        help="Language code for forced alignment (e.g. en, fr, de, es, it).",
    )
    parser.add_argument(
        "--hf-token",
        default=None,
        help="HuggingFace token. If omitted, HF_TOKEN from the environment is used.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only create the combined audio file and metadata without running diarization.",
    )
    parser.add_argument(
        "--retranscribe",
        action="store_true",
        help="Re-run ASR on the combined audio instead of using the logged transcribe-live text.",
    )
    args = parser.parse_args(argv)

    if args.end <= args.start:
        parser.error("--end must be later than --start on the same day.")
    if args.speakers is not None and (
        args.min_speakers is not None or args.max_speakers is not None
    ):
        parser.error("Use either --speakers or --min-speakers/--max-speakers, not both.")
    return args


def load_segments(log_path: Path) -> list[LiveSegment]:
    """Load saved audio segments from a transcribe-live JSONL log."""
    segments: list[LiveSegment] = []
    with log_path.expanduser().open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            entry = json.loads(line)
            audio_file = entry.get("audio_file")
            timestamp = entry.get("timestamp")
            if not audio_file or not timestamp:
                continue
            segments.append(
                LiveSegment(
                    timestamp=datetime.fromisoformat(timestamp),
                    audio_file=Path(audio_file).expanduser(),
                    duration_seconds=float(entry.get("duration_seconds") or 0.0),
                    raw_output=entry.get("raw_output"),
                ),
            )
    segments.sort(key=lambda segment: segment.timestamp)
    return _dedupe_segments(segments)


def _dedupe_segments(segments: list[LiveSegment]) -> list[LiveSegment]:
    """Deduplicate segments by audio file while preserving order."""
    deduped: list[LiveSegment] = []
    seen: set[Path] = set()
    for segment in segments:
        if segment.audio_file in seen:
            continue
        deduped.append(segment)
        seen.add(segment.audio_file)
    return deduped


def select_segments_in_range(
    segments: list[LiveSegment],
    *,
    target_date: date,
    start_time: time,
    end_time: time,
) -> list[LiveSegment]:
    """Select segments whose timestamps fall within the requested local time window."""
    selected: list[LiveSegment] = []
    for segment in segments:
        segment_date = segment.timestamp.date()
        segment_time = time(
            hour=segment.timestamp.hour,
            minute=segment.timestamp.minute,
            second=segment.timestamp.second,
        )
        if segment_date == target_date and start_time <= segment_time <= end_time:
            selected.append(segment)
    return selected


def session_basename(segments: list[LiveSegment]) -> str:
    """Create a stable basename for output files."""
    start = segments[0].timestamp.strftime("%Y%m%d_%H%M%S")
    end = segments[-1].timestamp.strftime("%H%M%S")
    return f"live_{start}_{end}"


def write_ffconcat_manifest(segments: list[LiveSegment], manifest_path: Path) -> None:
    """Write an ffconcat manifest for the selected MP3 files."""
    lines = ["ffconcat version 1.0"]
    for segment in segments:
        escaped = str(segment.audio_file).replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"file '{escaped}'")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def combine_segments(manifest_path: Path, output_wav: Path) -> None:
    """Combine the MP3 chunks into a single WAV file."""
    if shutil.which("ffmpeg") is None:
        msg = "ffmpeg is required to combine transcribe-live audio chunks."
        raise RuntimeError(msg)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest_path),
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    subprocess.run(cmd, check=True)


def build_retranscribe_request(args: argparse.Namespace, combined_audio: Path) -> dict[str, Any]:
    """Build metadata describing the internal retranscribe request."""
    if args.speakers is not None:
        min_speakers = args.speakers
        max_speakers = args.speakers
    else:
        min_speakers = args.min_speakers
        max_speakers = args.max_speakers
    return {
        "audio_file": str(combined_audio),
        "diarize_format": args.diarize_format,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
        "align_words": args.align_words,
        "align_language": args.align_language,
        "hf_token": bool(args.hf_token or os.environ.get("HF_TOKEN")),
    }


def transcript_suffix(diarize_format: str) -> str:
    """Return the output suffix for the diarized transcript."""
    return ".json" if diarize_format == "json" else ".txt"


def build_logged_transcript(segments: list[LiveSegment]) -> str:
    """Concatenate logged segment text into one transcript."""
    parts = [
        segment.raw_output.strip()
        for segment in segments
        if segment.raw_output and segment.raw_output.strip()
    ]
    return " ".join(parts)


def _shift_words(words: list[AlignedWord], offset_seconds: float) -> list[AlignedWord]:
    """Shift aligned word timestamps onto the combined-audio timeline."""
    return [
        AlignedWord(
            word=word.word,
            start=word.start + offset_seconds,
            end=word.end + offset_seconds,
        )
        for word in words
    ]


def _logged_alignment_device() -> str:
    """Pick a practical device for per-chunk forced alignment."""
    import torch  # noqa: PLC0415

    return "cuda" if torch.cuda.is_available() else "cpu"


def align_logged_segments_with_speakers(
    *,
    segments: list[LiveSegment],
    speaker_segments: list[DiarizedSegment],
    language: str = "en",
) -> list[DiarizedSegment]:
    """Align each logged chunk separately, then assign speakers on the combined timeline.

    `transcribe-live` chunk boundaries come from silence detection, so individual chunks
    can still contain multiple speakers. Running forced alignment per chunk keeps memory
    bounded while still allowing speaker changes inside a chunk.
    """
    all_words: list[AlignedWord] = []
    offset_seconds = 0.0
    alignment_device = _logged_alignment_device()

    for segment in segments:
        transcript = segment.raw_output.strip() if segment.raw_output else ""
        if transcript:
            words = align(
                segment.audio_file,
                transcript,
                language=language,
                device=alignment_device,
            )
            all_words.extend(_shift_words(words, offset_seconds))
        offset_seconds += max(segment.duration_seconds, 0.0)

    if not all_words:
        msg = "Forced alignment returned no words for the selected transcribe-live segments."
        raise RuntimeError(msg)
    return align_words_to_speakers(all_words, speaker_segments)


def ensure_hf_token(args: argparse.Namespace) -> None:
    """Validate that a HuggingFace token is available when not in prepare-only mode."""
    if args.prepare_only:
        return
    if args.hf_token or os.environ.get("HF_TOKEN"):
        return
    msg = "HF_TOKEN is required. Set HF_TOKEN in the environment or pass --hf-token."
    raise RuntimeError(msg)


def save_metadata(
    *,
    metadata_path: Path,
    segments: list[LiveSegment],
    combined_audio: Path,
    transcript_path: Path,
    mode: str,
    retranscribe_request: dict[str, Any] | None,
) -> None:
    """Persist the selected session metadata for debugging and replay."""
    payload: dict[str, Any] = {
        "mode": mode,
        "combined_audio": str(combined_audio),
        "transcript_path": str(transcript_path),
        "segment_count": len(segments),
        "segment_files": [str(segment.audio_file) for segment in segments],
        "timestamps": [segment.timestamp.isoformat() for segment in segments],
        "logged_transcript_length": len(build_logged_transcript(segments)),
        "retranscribe_request": retranscribe_request,
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_logged_diarization(
    *,
    args: argparse.Namespace,
    segments: list[LiveSegment],
    combined_audio: Path,
    transcript_path: Path,
) -> None:
    """Run diarization using the transcript already logged by transcribe-live.

    `transcribe-live` chunks are split on silence, not speaker changes, so a single
    saved MP3 can contain multiple speakers. Preserve those intra-chunk speaker turns
    by aligning each chunk independently and mapping the aligned words onto the
    combined-audio speaker timeline.
    """
    transcript = build_logged_transcript(segments)
    if not transcript:
        msg = "No raw_output text found in the selected transcribe-live log entries."
        raise RuntimeError(msg)

    hf_token = args.hf_token or os.environ.get("HF_TOKEN")
    assert hf_token is not None

    diarizer = SpeakerDiarizer(
        hf_token=hf_token,
        min_speakers=args.speakers if args.speakers is not None else args.min_speakers,
        max_speakers=args.speakers if args.speakers is not None else args.max_speakers,
    )
    print(f"Running diarization on device: {diarizer.device}")
    speaker_segments = diarizer.diarize(combined_audio)
    if not speaker_segments:
        msg = "Diarization returned no speaker segments."
        raise RuntimeError(msg)

    speaker_segments = align_logged_segments_with_speakers(
        segments=segments,
        speaker_segments=speaker_segments,
        language=args.align_language,
    )

    formatted = format_diarized_output(
        speaker_segments,
        output_format=args.diarize_format,
    )
    transcript_path.write_text(formatted.rstrip() + "\n", encoding="utf-8")


def _option_default(option: Any) -> Any:
    """Extract a Typer option's default value."""
    return getattr(option, "default", option)


def _option_env_value(option: Any) -> str | None:
    """Read the first configured env var value for a Typer option, if any."""
    envvar = getattr(option, "envvar", None)
    if isinstance(envvar, str):
        return os.environ.get(envvar)
    if isinstance(envvar, (list, tuple)):
        for name in envvar:
            value = os.environ.get(name)
            if value is not None:
                return value
    return None


def _resolve_option(option: Any) -> Any:
    """Resolve a Typer option from environment or fallback default."""
    env_value = _option_env_value(option)
    if env_value is None:
        return _option_default(option)
    default = _option_default(option)
    if isinstance(default, int):
        return int(env_value)
    return env_value


def run_retranscribe(
    args: argparse.Namespace,
    combined_audio: Path,
    transcript_path: Path,
) -> None:
    """Run the file-transcription pipeline internally and save the transcript to disk."""
    from agent_cli.agents.transcribe import _async_main  # noqa: PLC0415

    provider_cfg = agent_config.ProviderSelection(
        asr_provider=_resolve_option(opts.ASR_PROVIDER),
        llm_provider=_resolve_option(opts.LLM_PROVIDER),
        tts_provider="wyoming",
    )
    general_cfg = agent_config.General(
        log_level="warning",
        log_file=None,
        quiet=True,
        list_devices=False,
        clipboard=False,
    )
    wyoming_asr_cfg = agent_config.WyomingASR(
        asr_wyoming_ip=_resolve_option(opts.ASR_WYOMING_IP),
        asr_wyoming_port=_resolve_option(opts.ASR_WYOMING_PORT),
    )
    openai_base_url = _resolve_option(opts.OPENAI_BASE_URL)
    openai_asr_cfg = agent_config.OpenAIASR(
        asr_openai_model=_resolve_option(opts.ASR_OPENAI_MODEL),
        openai_api_key=_resolve_option(opts.OPENAI_API_KEY),
        openai_base_url=_resolve_option(opts.ASR_OPENAI_BASE_URL) or openai_base_url,
        asr_openai_prompt=_resolve_option(opts.ASR_OPENAI_PROMPT),
    )
    gemini_asr_cfg = agent_config.GeminiASR(
        asr_gemini_model=_resolve_option(opts.ASR_GEMINI_MODEL),
        gemini_api_key=_resolve_option(opts.GEMINI_API_KEY),
    )
    diarization_cfg = agent_config.Diarization(
        diarize=True,
        diarize_format=args.diarize_format,
        hf_token=args.hf_token or os.environ.get("HF_TOKEN"),
        min_speakers=args.speakers if args.speakers is not None else args.min_speakers,
        max_speakers=args.speakers if args.speakers is not None else args.max_speakers,
        align_words=args.align_words,
        align_language=args.align_language,
    )
    result = asyncio.run(
        _async_main(
            audio_file_path=combined_audio,
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=agent_config.Ollama(
                llm_ollama_model=_resolve_option(opts.LLM_OLLAMA_MODEL),
                llm_ollama_host=_resolve_option(opts.LLM_OLLAMA_HOST),
            ),
            openai_llm_cfg=agent_config.OpenAILLM(
                llm_openai_model=_resolve_option(opts.LLM_OPENAI_MODEL),
                openai_api_key=_resolve_option(opts.OPENAI_API_KEY),
                openai_base_url=openai_base_url,
            ),
            gemini_llm_cfg=agent_config.GeminiLLM(
                llm_gemini_model=_resolve_option(opts.LLM_GEMINI_MODEL),
                gemini_api_key=_resolve_option(opts.GEMINI_API_KEY),
            ),
            llm_enabled=False,
            transcription_log=None,
            diarization_cfg=diarization_cfg,
            emit_output=False,
            raise_diarization_errors=True,
        ),
    )

    transcript = result.get("transcript")
    if not isinstance(transcript, str) or not transcript:
        msg = "Transcribe returned no transcript."
        raise RuntimeError(msg)

    if transcript_path.suffix == ".json":
        transcript_path.write_text(transcript + "\n", encoding="utf-8")
    else:
        transcript_path.write_text(transcript.rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Argparse entry point used by the Typer command and tests."""
    args = parse_args(argv)
    log_path = args.transcription_log.expanduser()
    if not log_path.exists():
        msg = f"Transcription log not found: {log_path}"
        raise FileNotFoundError(msg)

    segments = load_segments(log_path)
    selected = select_segments_in_range(
        segments,
        target_date=args.date,
        start_time=args.start,
        end_time=args.end,
    )
    if not selected:
        msg = (
            f"No audio segments found in {log_path} for "
            f"{args.date.isoformat()} {args.start} to {args.end}."
        )
        raise RuntimeError(msg)

    missing = [segment.audio_file for segment in selected if not segment.audio_file.exists()]
    if missing:
        missing_list = "\n".join(str(path) for path in missing)
        msg = f"Selected audio files are missing:\n{missing_list}"
        raise FileNotFoundError(msg)

    ensure_hf_token(args)

    basename = session_basename(selected)
    output_dir = args.output_dir.expanduser() / args.date.strftime("%Y/%m/%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{basename}.ffconcat"
    combined_audio = output_dir / f"{basename}.wav"
    transcript_path = output_dir / f"{basename}{transcript_suffix(args.diarize_format)}"
    metadata_path = output_dir / f"{basename}.metadata.json"

    write_ffconcat_manifest(selected, manifest_path)
    combine_segments(manifest_path, combined_audio)

    retranscribe_request = build_retranscribe_request(args, combined_audio)
    save_metadata(
        metadata_path=metadata_path,
        segments=selected,
        combined_audio=combined_audio,
        transcript_path=transcript_path,
        mode="retranscribe" if args.retranscribe else "log_transcript",
        retranscribe_request=retranscribe_request if args.retranscribe else None,
    )

    print(f"Combined {len(selected)} segment(s) into {combined_audio}")
    if args.prepare_only:
        if args.retranscribe:
            print("Prepared combined audio and metadata for internal re-transcription.")
        else:
            print("Prepared combined audio and metadata for logged-transcript diarization.")
        print(f"Metadata saved to {metadata_path}")
        return 0

    if args.retranscribe:
        run_retranscribe(args, combined_audio, transcript_path)
    else:
        run_logged_diarization(
            args=args,
            segments=selected,
            combined_audio=combined_audio,
            transcript_path=transcript_path,
        )
    print(f"Saved diarized transcript to {transcript_path}")
    print(f"Metadata saved to {metadata_path}")
    return 0


def _build_cli_argv(
    *,
    date_value: str | None,
    start: str,
    end: str,
    transcription_log: Path,
    output_dir: Path,
    diarize_format: str,
    speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
    align_words: bool,
    align_language: str,
    hf_token: str | None,
    prepare_only: bool,
    retranscribe: bool,
) -> list[str]:
    """Translate Typer options into the shared argparse argv."""
    argv = [
        "--date",
        date_value or datetime.now().astimezone().date().isoformat(),
        "--start",
        start,
        "--end",
        end,
        "--transcription-log",
        str(transcription_log),
        "--output-dir",
        str(output_dir),
        "--diarize-format",
        diarize_format,
        "--align-language",
        align_language,
    ]
    if speakers is not None:
        argv.extend(["--speakers", str(speakers)])
    if min_speakers is not None:
        argv.extend(["--min-speakers", str(min_speakers)])
    if max_speakers is not None:
        argv.extend(["--max-speakers", str(max_speakers)])
    if align_words:
        argv.append("--align-words")
    if hf_token:
        argv.extend(["--hf-token", hf_token])
    if prepare_only:
        argv.append("--prepare-only")
    if retranscribe:
        argv.append("--retranscribe")
    return argv


@app.command("diarize-live-session", rich_help_panel="Voice Commands")
@requires_extras("diarization", process_name="diarize-live-session")
def diarize_live_session(
    *,
    date_value: str | None = typer.Option(
        None,
        "--date",
        help="Date of the live session in YYYY-MM-DD format. Defaults to today.",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        help="Start time of the session in HH:MM or HH:MM:SS.",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        help="End time of the session in HH:MM or HH:MM:SS.",
    ),
    transcription_log: Path = TRANSCRIPTION_LOG_OPTION,
    output_dir: Path = OUTPUT_DIR_OPTION,
    diarize_format: opts.DiarizeFormat = opts.DIARIZE_FORMAT,
    speakers: int | None = typer.Option(
        None,
        "--speakers",
        help="Known number of speakers. Sets both --min-speakers and --max-speakers.",
        rich_help_panel="Diarization",
    ),
    min_speakers: int | None = opts.MIN_SPEAKERS,
    max_speakers: int | None = opts.MAX_SPEAKERS,
    align_words: bool = ALIGN_WORDS_OPTION,
    align_language: str = opts.ALIGN_LANGUAGE,
    hf_token: str | None = opts.HF_TOKEN,
    prepare_only: bool = PREPARE_ONLY_OPTION,
    retranscribe: bool = RETRANSCRIBE_OPTION,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Diarize a saved `transcribe-live` window by combining its recorded chunks.

    By default this reuses the transcript text already logged by `transcribe-live`,
    aligns each saved chunk separately, and assigns speakers on the combined session
    timeline. Use `--retranscribe` if you want to re-run ASR on the combined audio.

    Examples:
    - `agent-cli diarize-live-session --date 2026-04-22 --start 11:32 --end 12:29 --speakers 3`
    - `agent-cli diarize-live-session --start 09:00 --end 09:30 --prepare-only`
    - `agent-cli diarize-live-session --date 2026-04-22 --start 11:32 --end 12:29 --diarize-format json`

    """
    if print_args:
        print_command_line_args(locals())

    argv = _build_cli_argv(
        date_value=date_value,
        start=start,
        end=end,
        transcription_log=transcription_log,
        output_dir=output_dir,
        diarize_format=diarize_format,
        speakers=speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        align_words=align_words,
        align_language=align_language,
        hf_token=hf_token,
        prepare_only=prepare_only,
        retranscribe=retranscribe,
    )
    try:
        exit_code = main(argv)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print_with_style(f"❌ {exc}", style="red")
        raise typer.Exit(1) from None
    if exit_code:
        raise typer.Exit(exit_code)
