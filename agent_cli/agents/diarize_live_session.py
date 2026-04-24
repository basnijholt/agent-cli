"""Retroactively diarize `transcribe-live` sessions from saved audio chunks."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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

if TYPE_CHECKING:
    from typer.models import OptionInfo


@dataclass(frozen=True)
class LiveSegment:
    """A saved `transcribe-live` segment."""

    timestamp: datetime
    audio_file: Path
    duration_seconds: float
    raw_output: str | None = None


@dataclass(frozen=True)
class DiarizeLiveSessionOptions:
    """Options for retroactive live-session diarization."""

    date: date
    start: time
    end: time
    transcription_log: Path = DEFAULT_TRANSCRIPTION_LOG
    output_dir: Path = DEFAULT_OUTPUT_DIR
    diarize_format: opts.DiarizeFormat = "inline"
    speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    align_words: bool = False
    align_language: str = "en"
    hf_token: str | None = None
    prepare_only: bool = False
    retranscribe: bool = False

    def __post_init__(self) -> None:
        """Validate option combinations."""
        if self.end <= self.start:
            msg = "--end must be later than --start on the same day."
            raise ValueError(msg)
        if self.speakers is not None and (
            self.min_speakers is not None or self.max_speakers is not None
        ):
            msg = "Use either --speakers or --min-speakers/--max-speakers, not both."
            raise ValueError(msg)
        if self.diarize_format not in {"inline", "json"}:
            msg = "diarize_format must be 'inline' or 'json'."
            raise ValueError(msg)


@lru_cache(maxsize=2048)
def _saved_audio_duration_seconds(audio_path: Path) -> float:
    """Return the decoded duration of a saved audio chunk."""
    import torchaudio  # noqa: PLC0415

    try:
        metadata = torchaudio.info(str(audio_path))
    except (OSError, RuntimeError, ValueError):
        metadata = None

    if metadata is None or metadata.sample_rate <= 0 or metadata.num_frames <= 0:
        waveform, sample_rate = torchaudio.load(str(audio_path))
        return waveform.shape[-1] / sample_rate
    return metadata.num_frames / metadata.sample_rate


def parse_clock_time(value: str) -> time:
    """Parse HH:MM or HH:MM:SS."""
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        msg = f"Invalid time value: {value!r}. Use HH:MM or HH:MM:SS."
        raise ValueError(msg) from exc


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
    """Select segments whose audio overlaps the requested local time window."""
    selected: list[LiveSegment] = []
    for segment in segments:
        tzinfo = segment.timestamp.tzinfo
        window_start = datetime.combine(target_date, start_time, tzinfo=tzinfo)
        window_end = datetime.combine(target_date, end_time, tzinfo=tzinfo)
        segment_end = segment.timestamp
        duration_seconds = max(segment.duration_seconds, 0.0)
        if segment.audio_file.exists():
            duration_seconds = _saved_audio_duration_seconds(segment.audio_file)
        segment_start = segment_end - timedelta(seconds=duration_seconds)
        if segment_end >= window_start and segment_start <= window_end:
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


def build_retranscribe_request(
    options: DiarizeLiveSessionOptions,
    combined_audio: Path,
) -> dict[str, Any]:
    """Build metadata describing the internal retranscribe request."""
    min_speakers: int | None
    max_speakers: int | None
    if options.speakers is not None:
        min_speakers = options.speakers
        max_speakers = options.speakers
    else:
        min_speakers = options.min_speakers
        max_speakers = options.max_speakers
    return {
        "audio_file": str(combined_audio),
        "diarize_format": options.diarize_format,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
        "align_words": options.align_words,
        "align_language": options.align_language,
        "hf_token": bool(options.hf_token or os.environ.get("HF_TOKEN")),
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
        offset_seconds += _saved_audio_duration_seconds(segment.audio_file)

    if not all_words:
        msg = "Forced alignment returned no words for the selected transcribe-live segments."
        raise RuntimeError(msg)
    return align_words_to_speakers(all_words, speaker_segments)


def ensure_hf_token(options: DiarizeLiveSessionOptions) -> None:
    """Validate that a HuggingFace token is available when not in prepare-only mode."""
    if options.prepare_only:
        return
    if options.hf_token or os.environ.get("HF_TOKEN"):
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
    options: DiarizeLiveSessionOptions,
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

    hf_token = options.hf_token or os.environ.get("HF_TOKEN")
    assert hf_token is not None

    diarizer = SpeakerDiarizer(
        hf_token=hf_token,
        min_speakers=options.speakers if options.speakers is not None else options.min_speakers,
        max_speakers=options.speakers if options.speakers is not None else options.max_speakers,
    )
    print(f"Running diarization on device: {diarizer.device}")
    speaker_segments = diarizer.diarize(combined_audio)
    if not speaker_segments:
        msg = "Diarization returned no speaker segments."
        raise RuntimeError(msg)

    speaker_segments = align_logged_segments_with_speakers(
        segments=segments,
        speaker_segments=speaker_segments,
        language=options.align_language,
    )

    formatted = format_diarized_output(
        speaker_segments,
        output_format=options.diarize_format,
    )
    transcript_path.write_text(formatted.rstrip() + "\n", encoding="utf-8")


def _option_default(option: Any) -> Any:
    """Extract a Typer option's default value."""
    return cast("OptionInfo", option).default


def _option_env_value(option: Any) -> str | None:
    """Read the first configured env var value for a Typer option, if any."""
    envvar = cast("OptionInfo", option).envvar
    if isinstance(envvar, str):
        return os.environ.get(envvar)
    if isinstance(envvar, (list, tuple)):
        for name in envvar:
            value = os.environ.get(name)
            if value is not None:
                return value
    return None


def _coerce_option_value(option: Any, value: Any) -> Any:
    """Coerce config/env values to the target option's runtime type."""
    default = _option_default(option)
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return value


def _load_transcribe_config_defaults(config_file: str | None) -> dict[str, Any]:
    """Load `[defaults]` and `[transcribe]` config values for retranscription."""
    loaded = agent_config.load_config(config_file)
    defaults = agent_config.normalize_provider_defaults(loaded.get("defaults", {}))
    transcribe_defaults = agent_config.normalize_provider_defaults(loaded.get("transcribe", {}))
    return {**defaults, **transcribe_defaults}


def _resolve_transcribe_option(
    name: str,
    option: Any,
    config_defaults: dict[str, Any],
) -> Any:
    """Resolve retranscribe settings with CLI-equivalent precedence."""
    env_value = _option_env_value(option)
    if env_value is not None:
        return _coerce_option_value(option, env_value)
    if name in config_defaults:
        return _coerce_option_value(option, config_defaults[name])
    return _option_default(option)


def run_retranscribe(
    options: DiarizeLiveSessionOptions,
    combined_audio: Path,
    transcript_path: Path,
    *,
    config_file: str | None = None,
) -> None:
    """Run the file-transcription pipeline internally and save the transcript to disk."""
    from agent_cli.agents.transcribe import _async_main  # noqa: PLC0415

    config_defaults = _load_transcribe_config_defaults(config_file)

    provider_cfg = agent_config.ProviderSelection(
        asr_provider=_resolve_transcribe_option(
            "asr_provider",
            opts.ASR_PROVIDER,
            config_defaults,
        ),
        llm_provider=_resolve_transcribe_option(
            "llm_provider",
            opts.LLM_PROVIDER,
            config_defaults,
        ),
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
        asr_wyoming_ip=_resolve_transcribe_option(
            "asr_wyoming_ip",
            opts.ASR_WYOMING_IP,
            config_defaults,
        ),
        asr_wyoming_port=_resolve_transcribe_option(
            "asr_wyoming_port",
            opts.ASR_WYOMING_PORT,
            config_defaults,
        ),
    )
    openai_base_url = _resolve_transcribe_option(
        "openai_base_url",
        opts.OPENAI_BASE_URL,
        config_defaults,
    )
    openai_asr_cfg = agent_config.OpenAIASR(
        asr_openai_model=_resolve_transcribe_option(
            "asr_openai_model",
            opts.ASR_OPENAI_MODEL,
            config_defaults,
        ),
        openai_api_key=_resolve_transcribe_option(
            "openai_api_key",
            opts.OPENAI_API_KEY,
            config_defaults,
        ),
        openai_base_url=_resolve_transcribe_option(
            "asr_openai_base_url",
            opts.ASR_OPENAI_BASE_URL,
            config_defaults,
        )
        or openai_base_url,
        asr_openai_prompt=_resolve_transcribe_option(
            "asr_openai_prompt",
            opts.ASR_OPENAI_PROMPT,
            config_defaults,
        ),
    )
    gemini_asr_cfg = agent_config.GeminiASR(
        asr_gemini_model=_resolve_transcribe_option(
            "asr_gemini_model",
            opts.ASR_GEMINI_MODEL,
            config_defaults,
        ),
        gemini_api_key=_resolve_transcribe_option(
            "gemini_api_key",
            opts.GEMINI_API_KEY,
            config_defaults,
        ),
    )
    diarization_cfg = agent_config.Diarization(
        diarize=True,
        diarize_format=options.diarize_format,
        hf_token=options.hf_token or os.environ.get("HF_TOKEN"),
        min_speakers=options.speakers if options.speakers is not None else options.min_speakers,
        max_speakers=options.speakers if options.speakers is not None else options.max_speakers,
        align_words=options.align_words,
        align_language=options.align_language,
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
                llm_ollama_model=_resolve_transcribe_option(
                    "llm_ollama_model",
                    opts.LLM_OLLAMA_MODEL,
                    config_defaults,
                ),
                llm_ollama_host=_resolve_transcribe_option(
                    "llm_ollama_host",
                    opts.LLM_OLLAMA_HOST,
                    config_defaults,
                ),
            ),
            openai_llm_cfg=agent_config.OpenAILLM(
                llm_openai_model=_resolve_transcribe_option(
                    "llm_openai_model",
                    opts.LLM_OPENAI_MODEL,
                    config_defaults,
                ),
                openai_api_key=_resolve_transcribe_option(
                    "openai_api_key",
                    opts.OPENAI_API_KEY,
                    config_defaults,
                ),
                openai_base_url=openai_base_url,
            ),
            gemini_llm_cfg=agent_config.GeminiLLM(
                llm_gemini_model=_resolve_transcribe_option(
                    "llm_gemini_model",
                    opts.LLM_GEMINI_MODEL,
                    config_defaults,
                ),
                gemini_api_key=_resolve_transcribe_option(
                    "gemini_api_key",
                    opts.GEMINI_API_KEY,
                    config_defaults,
                ),
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


def run_session(options: DiarizeLiveSessionOptions, *, config_file: str | None = None) -> int:
    """Diarize a selected live session window."""
    log_path = options.transcription_log.expanduser()
    if not log_path.exists():
        msg = f"Transcription log not found: {log_path}"
        raise FileNotFoundError(msg)

    segments = load_segments(log_path)
    selected = select_segments_in_range(
        segments,
        target_date=options.date,
        start_time=options.start,
        end_time=options.end,
    )
    if not selected:
        msg = (
            f"No audio segments found in {log_path} for "
            f"{options.date.isoformat()} {options.start} to {options.end}."
        )
        raise RuntimeError(msg)

    missing = [segment.audio_file for segment in selected if not segment.audio_file.exists()]
    if missing:
        missing_list = "\n".join(str(path) for path in missing)
        msg = f"Selected audio files are missing:\n{missing_list}"
        raise FileNotFoundError(msg)

    ensure_hf_token(options)

    basename = session_basename(selected)
    output_dir = options.output_dir.expanduser() / options.date.strftime("%Y/%m/%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{basename}.ffconcat"
    combined_audio = output_dir / f"{basename}.wav"
    transcript_path = output_dir / f"{basename}{transcript_suffix(options.diarize_format)}"
    metadata_path = output_dir / f"{basename}.metadata.json"

    write_ffconcat_manifest(selected, manifest_path)
    combine_segments(manifest_path, combined_audio)

    retranscribe_request = build_retranscribe_request(options, combined_audio)
    save_metadata(
        metadata_path=metadata_path,
        segments=selected,
        combined_audio=combined_audio,
        transcript_path=transcript_path,
        mode="retranscribe" if options.retranscribe else "log_transcript",
        retranscribe_request=retranscribe_request if options.retranscribe else None,
    )

    print(f"Combined {len(selected)} segment(s) into {combined_audio}")
    if options.prepare_only:
        if options.retranscribe:
            print("Prepared combined audio and metadata for internal re-transcription.")
        else:
            print("Prepared combined audio and metadata for logged-transcript diarization.")
        print(f"Metadata saved to {metadata_path}")
        return 0

    if options.retranscribe:
        run_retranscribe(
            options,
            combined_audio,
            transcript_path,
            config_file=config_file,
        )
    else:
        run_logged_diarization(
            options=options,
            segments=selected,
            combined_audio=combined_audio,
            transcript_path=transcript_path,
        )
    print(f"Saved diarized transcript to {transcript_path}")
    print(f"Metadata saved to {metadata_path}")
    return 0


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

    try:
        options = DiarizeLiveSessionOptions(
            date=date.fromisoformat(date_value)
            if date_value
            else datetime.now().astimezone().date(),
            start=parse_clock_time(start),
            end=parse_clock_time(end),
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
        exit_code = run_session(options, config_file=config_file)
    except (
        FileNotFoundError,
        RuntimeError,
        ValueError,
        subprocess.CalledProcessError,
    ) as exc:
        print_with_style(f"❌ {exc}", style="red")
        raise typer.Exit(1) from None
    if exit_code:
        raise typer.Exit(exit_code)
