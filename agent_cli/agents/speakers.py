"""Manage persistent diarization speaker profiles."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any

import typer
from rich.markup import escape
from rich.table import Table

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.deps import requires_extras
from agent_cli.core.diarization import (
    DEFAULT_CLEAN_SPEAKER_NEIGHBOR_GAP_SECONDS,
    DiarizedSegment,
    SpeakerDiarizer,
    best_clean_speaker_segment,
)
from agent_cli.core.process import set_process_title
from agent_cli.core.speaker_identity import (
    DEFAULT_SPEAKER_PROFILES_FILE,
    SpeakerMatch,
    add_speaker_embedding_to_profile,
    create_speaker_profile_from_embedding,
    extract_speaker_embeddings,
    load_speaker_profile_store,
    match_speaker_profiles,
    merge_speaker_profiles,
    rename_speaker_profile,
    save_speaker_profile_store,
    summarize_speaker_profile,
    summarize_speaker_profiles,
)
from agent_cli.core.utils import console
from agent_cli.services.asr import get_last_recording

speakers_app = typer.Typer(
    name="speakers",
    help="""Manage persistent diarization speaker identities.

Speaker profiles are created by diarization with `--remember-unknown-speakers`
or `--enroll-speakers`. Use this command to inspect those profiles, rename
stable `UNKNOWN_###` identities, or merge duplicate profiles without re-running
diarization.
""",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)

app.add_typer(speakers_app, name="speakers", rich_help_panel="Voice Commands")

SPEAKER_PROFILES_FILE_OPTION: Path = typer.Option(
    DEFAULT_SPEAKER_PROFILES_FILE,
    "--speaker-profiles-file",
    help="JSON file storing persistent speaker voice embeddings.",
)
DEFAULT_REVIEW_TRANSCRIPTION_LOG = Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"
DEFAULT_REVIEW_STATE_FILE = Path.home() / ".config" / "agent-cli" / "speaker-review-state.json"
REVIEW_SKIPPED_EMBEDDING_NEAR_DUPLICATE_THRESHOLD = 0.98
REVIEW_MIN_PROMPT_SEGMENT_SECONDS = 2.0
REVIEW_SNIPPET_NEIGHBOR_GAP_SECONDS = DEFAULT_CLEAN_SPEAKER_NEIGHBOR_GAP_SECONDS
REVIEW_TRANSCRIPTION_LOG_OPTION: Path = typer.Option(
    DEFAULT_REVIEW_TRANSCRIPTION_LOG,
    "--transcription-log",
    help="Path to the transcribe-live JSONL log for --last-session.",
)
REVIEW_STATE_FILE_OPTION: Path = typer.Option(
    DEFAULT_REVIEW_STATE_FILE,
    "--review-state-file",
    help="JSON cache tracking which audio files have already been speaker-reviewed.",
)


@dataclass(frozen=True)
class _SpeakerReviewResult:
    changed: bool
    action: str
    target_profile_id: str | None = None
    target_display_name: str | None = None


class _ReviewInterruptedError(Exception):
    """Review was quit after zero or more profile changes."""

    def __init__(self, changed: bool, records: list[dict[str, Any]]) -> None:
        super().__init__()
        self.changed = changed
        self.records = records


@contextmanager
def _suppress_speaker_review_warnings() -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="torchcodec is not installed correctly.*",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="Mean of empty slice.*",
            category=RuntimeWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message="invalid value encountered in divide.*",
            category=RuntimeWarning,
        )
        yield


@speakers_app.callback()
def speakers_callback(ctx: typer.Context) -> None:
    """Speaker profile command group callback."""
    if ctx.invoked_subcommand is not None:
        set_process_title(f"speakers-{ctx.invoked_subcommand}")


def _load_store_or_exit(path: Path) -> dict[str, Any]:
    try:
        return load_speaker_profile_store(path)
    except (TypeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def _merge_command_hint(source: str, target: str) -> str:
    return f"speakers merge {shlex.quote(source)} {shlex.quote(target)}"


def _validate_single_review_source(
    *,
    from_file: Path | None,
    last_recording: int | None,
    last_session: int | None,
) -> None:
    selected = sum(value is not None for value in (from_file, last_recording, last_session))
    if selected > 1:
        msg = "Use only one of --from-file, --last-recording, or --last-session."
        raise ValueError(msg)


def _load_live_segments(log_path: Path) -> list[Any]:
    from agent_cli.agents.diarize_live_session import load_segments  # noqa: PLC0415

    expanded = log_path.expanduser()
    if not expanded.exists():
        msg = f"Transcription log not found: {expanded}"
        raise FileNotFoundError(msg)
    return load_segments(expanded)


def _select_recent_live_session_audio(
    *,
    last_session: int,
    transcription_log: Path,
    session_gap: float,
) -> list[Path]:
    from agent_cli.agents.diarize_live_session import select_recent_session  # noqa: PLC0415

    if last_session < 1:
        msg = "--last-session must be 1 or greater."
        raise ValueError(msg)
    selected = select_recent_session(
        _load_live_segments(transcription_log),
        index=last_session,
        max_gap_seconds=session_gap,
    )
    missing = [segment.audio_file for segment in selected if not segment.audio_file.exists()]
    if missing:
        missing_list = "\n".join(str(path) for path in missing)
        msg = f"Selected audio files are missing:\n{missing_list}"
        raise FileNotFoundError(msg)
    return [segment.audio_file for segment in reversed(selected)]


def _all_live_review_audio_targets(
    *,
    transcription_log: Path,
) -> list[Path]:
    try:
        segments = _load_live_segments(transcription_log)
    except FileNotFoundError:
        return []
    return [segment.audio_file for segment in reversed(segments) if segment.audio_file.exists()]


def _resolve_review_audio_targets(
    *,
    from_file: Path | None,
    last_recording: int | None,
    last_session: int | None,
    transcription_log: Path,
    session_gap: float,
) -> list[Path]:
    """Resolve the audio files that should be reviewed, newest first."""
    _validate_single_review_source(
        from_file=from_file,
        last_recording=last_recording,
        last_session=last_session,
    )

    if from_file is not None:
        path = from_file.expanduser()
        if not path.exists():
            msg = f"File not found: {path}"
            raise FileNotFoundError(msg)
        return [path]

    if last_session is not None:
        return _select_recent_live_session_audio(
            last_session=last_session,
            transcription_log=transcription_log,
            session_gap=session_gap,
        )

    if last_recording is not None:
        if last_recording < 1:
            msg = "--last-recording must be 1 or greater."
            raise ValueError(msg)
        recording = get_last_recording(last_recording)
        if recording is None:
            msg = f"Recording #{last_recording} not found."
            raise FileNotFoundError(msg)
        return [recording]

    live_targets = _all_live_review_audio_targets(transcription_log=transcription_log)
    if live_targets:
        return live_targets

    recording = get_last_recording(1)
    if recording is None:
        msg = "Recording #1 not found."
        raise FileNotFoundError(msg)
    return [recording]


def _new_review_state() -> dict[str, Any]:
    return {"version": 1, "audio_files": {}, "skipped_speakers": []}


def _load_review_state(path: Path) -> dict[str, Any]:
    path = path.expanduser()
    if not path.exists():
        return _new_review_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Invalid speaker review state file {path}: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Invalid speaker review state file {path}: expected a JSON object."
        raise TypeError(msg)
    audio_files = data.get("audio_files")
    if not isinstance(audio_files, dict):
        data["audio_files"] = {}
    skipped_speakers = data.get("skipped_speakers")
    if not isinstance(skipped_speakers, list):
        data["skipped_speakers"] = []
    data.setdefault("version", 1)
    return data


def _save_review_state(path: Path, state: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _audio_review_key(audio_path: Path) -> str:
    return str(audio_path.expanduser().resolve(strict=False))


def _audio_review_metadata(audio_path: Path) -> dict[str, Any]:
    stat = audio_path.expanduser().stat()
    return {
        "path": _audio_review_key(audio_path),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _audio_review_is_cached(
    state: dict[str, Any],
    audio_path: Path,
) -> bool:
    audio_files = state.get("audio_files", {})
    if not isinstance(audio_files, dict):
        return False
    entry = audio_files.get(_audio_review_key(audio_path))
    if not isinstance(entry, dict):
        return False
    try:
        metadata = _audio_review_metadata(audio_path)
    except OSError:
        return False
    return entry.get("size") == metadata["size"] and entry.get("mtime_ns") == metadata["mtime_ns"]


def _review_record_from_result(
    *,
    diarized_label: str,
    review_label: str,
    match: SpeakerMatch | None,
    result: _SpeakerReviewResult,
) -> dict[str, Any]:
    return {
        "diarized_label": diarized_label,
        "review_label": review_label,
        "profile_id": match.profile_id if match is not None else None,
        "display_name": match.display_name if match is not None else None,
        "similarity": match.similarity if match is not None else None,
        "action": result.action,
        "target_profile_id": result.target_profile_id,
        "target_display_name": result.target_display_name,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }


def _record_audio_review(
    state: dict[str, Any],
    audio_path: Path,
    records: list[dict[str, Any]],
) -> None:
    audio_files = state.setdefault("audio_files", {})
    if not isinstance(audio_files, dict):
        audio_files = {}
        state["audio_files"] = audio_files
    metadata = _audio_review_metadata(audio_path)
    audio_files[metadata["path"]] = {
        **metadata,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "speakers": records,
    }


def _review_cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _source_review_profile_id(
    store: dict[str, Any],
    match: SpeakerMatch | None,
) -> str | None:
    profile = _matched_profile(store, match)
    if profile is not None and bool(profile.get("anonymous")):
        return str(profile["id"])
    return None


def _skipped_speaker_entries(review_state: dict[str, Any]) -> list[dict[str, Any]]:
    skipped_speakers = review_state.setdefault("skipped_speakers", [])
    if not isinstance(skipped_speakers, list):
        skipped_speakers = []
        review_state["skipped_speakers"] = skipped_speakers
    return skipped_speakers


def _matching_skipped_speaker(
    review_state: dict[str, Any],
    *,
    source_profile_id: str | None,
    embedding: list[float] | None,
    threshold: float,
) -> dict[str, Any] | None:
    for entry in _skipped_speaker_entries(review_state):
        if not isinstance(entry, dict):
            continue
        if source_profile_id is not None and entry.get("profile_id") == source_profile_id:
            return entry
        entry_embeddings = entry.get("embeddings", [])
        if embedding is None or not isinstance(entry_embeddings, list):
            continue
        for entry_embedding in entry_embeddings:
            if not isinstance(entry_embedding, list):
                continue
            similarity = _review_cosine_similarity(embedding, entry_embedding)
            if similarity >= threshold:
                return entry
    return None


def _record_skipped_speaker(
    review_state: dict[str, Any],
    *,
    review_label: str,
    source_profile_id: str | None,
    embedding: list[float] | None,
) -> None:
    entries = _skipped_speaker_entries(review_state)
    entry = _matching_skipped_speaker(
        review_state,
        source_profile_id=source_profile_id,
        embedding=embedding,
        threshold=REVIEW_SKIPPED_EMBEDDING_NEAR_DUPLICATE_THRESHOLD,
    )
    now = datetime.now(UTC).isoformat()
    if entry is None:
        entry = {
            "id": source_profile_id or f"skipped_{len(entries) + 1:04d}",
            "profile_id": source_profile_id,
            "label": review_label,
            "embeddings": [],
            "created_at": now,
        }
        entries.append(entry)
    entry["label"] = review_label
    entry["updated_at"] = now
    if embedding is None:
        return
    embeddings = entry.setdefault("embeddings", [])
    if not isinstance(embeddings, list):
        embeddings = []
        entry["embeddings"] = embeddings
    for existing in embeddings:
        if isinstance(existing, list) and (
            _review_cosine_similarity(embedding, existing)
            >= REVIEW_SKIPPED_EMBEDDING_NEAR_DUPLICATE_THRESHOLD
        ):
            return
    embeddings.append(embedding)


def _speaker_labels_by_first_turn(segments: list[DiarizedSegment]) -> list[str]:
    first_seen: dict[str, float] = {}
    for segment in segments:
        first_seen.setdefault(segment.speaker, segment.start)
    return [label for label, _ in sorted(first_seen.items(), key=lambda item: item[1])]


def _write_speaker_snippet(
    *,
    audio_path: Path,
    segment: DiarizedSegment,
    output_dir: Path,
    seconds: float,
) -> Path:
    """Write a short audio snippet for one diarized speaker segment."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        msg = "ffmpeg is required to extract speaker review snippets."
        raise RuntimeError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)
    start = max(segment.start, 0.0)
    duration = max(min(segment.end - segment.start, seconds), 0.1)
    output_path = output_dir / f"{segment.speaker}_{int(start * 1000):08d}.wav"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(audio_path),
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_path),
        ],
        check=True,
    )
    return output_path


def _audio_player_command(player: str | None, audio_path: Path) -> list[str]:
    if player:
        parts = shlex.split(player)
        if not parts:
            msg = "--player cannot be empty."
            raise RuntimeError(msg)
        executable = parts[0] if Path(parts[0]).is_absolute() else shutil.which(parts[0])
        if executable is None:
            msg = f"Audio player not found: {parts[0]}"
            raise RuntimeError(msg)
        return [executable, *parts[1:], str(audio_path)]
    if sys.platform == "darwin" and (afplay := shutil.which("afplay")):
        return [afplay, str(audio_path)]
    if ffplay := shutil.which("ffplay"):
        return [ffplay, "-autoexit", "-nodisp", "-loglevel", "error", str(audio_path)]
    if aplay := shutil.which("aplay"):
        return [aplay, str(audio_path)]
    if paplay := shutil.which("paplay"):
        return [paplay, str(audio_path)]
    msg = "No audio player found. Install ffmpeg/ffplay or pass --player."
    raise RuntimeError(msg)


def _start_audio_playback(
    audio_path: Path,
    *,
    player: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start playing an audio file with a local command-line player."""
    return subprocess.Popen(
        _audio_player_command(player, audio_path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_audio_playback(
    process: subprocess.Popen[bytes] | None,
    *,
    timeout: float = 1.0,
) -> None:
    """Stop a playback process if it is still running."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            process.wait(timeout=timeout)
        except OSError:
            return


def _review_choice_prompt() -> str:
    return (
        typer.prompt(
            "Choose action",
            default="s",
        )
        .strip()
        .casefold()
    )


def _print_review_speaker_intro(
    *,
    label: str,
    embedding: list[float] | None,
    match: SpeakerMatch | None,
    source_profile_id: str | None,
) -> None:
    can_update_profile = embedding is not None or source_profile_id is not None
    console.print(f"\n[bold]Speaker:[/bold] [cyan]{label}[/cyan]")
    if match is not None:
        console.print(
            "[dim]Closest profile:[/dim] "
            f"[bold]{match.display_name}[/bold] "
            f"([cyan]{match.profile_id}[/cyan], {match.similarity:.2f})",
        )
    else:
        console.print("[dim]Closest profile:[/dim] none")
    if not can_update_profile:
        console.print(
            "[yellow]No embedding was available for this speaker; only skip/replay works.[/yellow]"
        )
        console.print(
            "[dim]Actions:[/dim] "
            "[bold]p[/bold]=replay, "
            "[bold]s[/bold]=skip, "
            "[bold]q[/bold]=save and quit",
        )
    else:
        name_action = "name this unknown speaker" if source_profile_id else "create a new profile"
        console.print(
            "[dim]Actions:[/dim] "
            "[bold]p[/bold]=replay, "
            "[bold]m[/bold]=merge into an existing named profile, "
            f"[bold]n[/bold]={name_action}, "
            "[bold]s[/bold]=skip, "
            "[bold]q[/bold]=save and quit",
        )


def _matched_profile(
    store: dict[str, Any],
    match: SpeakerMatch | None,
) -> dict[str, Any] | None:
    if match is None:
        return None
    profiles = store.get("profiles", [])
    if not isinstance(profiles, list):
        return None
    for profile in profiles:
        if isinstance(profile, dict) and str(profile.get("id")) == match.profile_id:
            return profile
    return None


def _is_named_review_match(
    *,
    store: dict[str, Any],
    match: SpeakerMatch | None,
) -> bool:
    profile = _matched_profile(store, match)
    return profile is not None and not bool(profile.get("anonymous"))


def _is_anonymous_review_match(
    *,
    store: dict[str, Any],
    match: SpeakerMatch | None,
) -> bool:
    profile = _matched_profile(store, match)
    return profile is not None and bool(profile.get("anonymous"))


def _review_label(
    *,
    diarized_label: str,
    store: dict[str, Any],
    match: SpeakerMatch | None,
) -> str:
    profile = _matched_profile(store, match)
    if profile is not None and bool(profile.get("anonymous")):
        return str(profile.get("id"))
    return diarized_label


def _start_review_snippet(
    snippet_path: Path,
    *,
    player: str | None,
) -> subprocess.Popen[bytes] | None:
    try:
        return _start_audio_playback(snippet_path, player=player)
    except (OSError, RuntimeError) as exc:
        console.print(f"[yellow]Could not play snippet: {exc}[/yellow]")
        return None


def _named_profile_options(
    store: dict[str, Any],
    *,
    exclude_profile_id: str | None = None,
) -> list[dict[str, Any]]:
    profiles = store.get("profiles", [])
    if not isinstance(profiles, list):
        return []
    return [
        profile
        for profile in profiles
        if isinstance(profile, dict)
        and not bool(profile.get("anonymous"))
        and str(profile.get("id")) != exclude_profile_id
    ]


def _print_merge_target_options(
    store: dict[str, Any],
    *,
    exclude_profile_id: str | None,
) -> list[dict[str, Any]]:
    options = _named_profile_options(store, exclude_profile_id=exclude_profile_id)
    if not options:
        console.print(
            "[yellow]No named profiles are available to merge into. Use new/name.[/yellow]"
        )
        return []
    console.print("[dim]Merge targets:[/dim]")
    for index, profile in enumerate(options, start=1):
        summary = summarize_speaker_profile(profile)
        console.print(
            f"  [bold]{index}[/bold]. [bold]{summary['display_name']}[/bold] "
            f"([cyan]{summary['id']}[/cyan])",
        )
    return options


def _resolve_merge_target_choice(
    choice: str,
    options: list[dict[str, Any]],
) -> str | None:
    clean_choice = choice.strip()
    if clean_choice.isdecimal():
        index = int(clean_choice)
        if 1 <= index <= len(options):
            return str(options[index - 1]["id"])
    for profile in options:
        summary = summarize_speaker_profile(profile)
        if clean_choice.casefold() in {
            str(summary["id"]).casefold(),
            str(summary["display_name"]).casefold(),
        }:
            return str(summary["id"])
    console.print("[yellow]Choose one of the listed profile numbers.[/yellow]")
    return None


def _prompt_merge_target(
    store: dict[str, Any],
    *,
    exclude_profile_id: str | None,
) -> str | None:
    options = _print_merge_target_options(store, exclude_profile_id=exclude_profile_id)
    if not options:
        return None
    default = "1" if len(options) == 1 else None
    target = typer.prompt("Merge into profile number", default=default).strip()
    return _resolve_merge_target_choice(target, options)


def _merge_review_speaker(
    *,
    label: str,
    embedding: list[float] | None,
    source_profile_id: str | None,
    store: dict[str, Any],
) -> dict[str, Any] | None:
    target = _prompt_merge_target(store, exclude_profile_id=source_profile_id)
    if target is None:
        return None
    try:
        if source_profile_id is not None:
            profile = merge_speaker_profiles(store, source_profile_id, target)
        else:
            if embedding is None:
                console.print("[yellow]Cannot merge this speaker without an embedding.[/yellow]")
                return None
            profile = add_speaker_embedding_to_profile(store, target, embedding)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return None
    summary = summarize_speaker_profile(profile)
    console.print(
        f"[green]Merged current speaker {label} into {summary['display_name']}.[/green]",
    )
    return summary


def _create_review_speaker(
    *,
    label: str,
    embedding: list[float] | None,
    source_profile_id: str | None,
    store: dict[str, Any],
) -> dict[str, Any] | None:
    prompt = "Speaker name" if source_profile_id is not None else "New speaker name"
    name = typer.prompt(prompt).strip()
    try:
        if source_profile_id is not None:
            profile = rename_speaker_profile(store, source_profile_id, name)
        else:
            if embedding is None:
                console.print(
                    "[yellow]Cannot create a speaker profile without an embedding.[/yellow]"
                )
                return None
            profile = create_speaker_profile_from_embedding(store, name, embedding)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return None
    summary = summarize_speaker_profile(profile)
    if source_profile_id is not None:
        console.print(
            f"[green]Named speaker {label} as {summary['display_name']}.[/green]",
        )
    else:
        console.print(f"[green]Created speaker profile {summary['display_name']}.[/green]")
    return summary


def _review_speaker(
    *,
    label: str,
    snippet_path: Path,
    embedding: list[float] | None,
    match: SpeakerMatch | None,
    store: dict[str, Any],
    player: str | None,
) -> _SpeakerReviewResult:
    """Interactively review one diarized speaker label."""
    source_profile = _matched_profile(store, match)
    source_profile_id = (
        str(source_profile["id"])
        if source_profile is not None and bool(source_profile.get("anonymous"))
        else None
    )
    play_requested = True
    while True:
        can_update_profile = embedding is not None or source_profile_id is not None
        _print_review_speaker_intro(
            label=label,
            embedding=embedding,
            match=match,
            source_profile_id=source_profile_id,
        )
        playback_process = (
            _start_review_snippet(snippet_path, player=player) if play_requested else None
        )
        play_requested = False

        try:
            choice = _review_choice_prompt()
        finally:
            _stop_audio_playback(playback_process)
        if choice in {"p", "play", "replay"}:
            play_requested = True
            continue
        if choice in {"s", "skip", ""}:
            console.print(f"[dim]Skipped {label}.[/dim]")
            return _SpeakerReviewResult(changed=False, action="skipped")
        if choice in {"q", "quit"}:
            raise typer.Exit(0)
        if not can_update_profile:
            console.print("[yellow]Choose p, s, or q; this speaker has no embedding.[/yellow]")
            continue
        if choice in {"m", "merge"}:
            summary = _merge_review_speaker(
                label=label,
                embedding=embedding,
                source_profile_id=source_profile_id,
                store=store,
            )
            if summary is not None:
                return _SpeakerReviewResult(
                    changed=True,
                    action="merged",
                    target_profile_id=str(summary["id"]),
                    target_display_name=str(summary["display_name"]),
                )
            continue
        if choice in {"n", "new", "name"}:
            summary = _create_review_speaker(
                label=label,
                embedding=embedding,
                source_profile_id=source_profile_id,
                store=store,
            )
            if summary is not None:
                return _SpeakerReviewResult(
                    changed=True,
                    action="named" if source_profile_id is not None else "created",
                    target_profile_id=str(summary["id"]),
                    target_display_name=str(summary["display_name"]),
                )
            continue
        if not can_update_profile:
            console.print("[yellow]Unknown choice. Use p, s, or q.[/yellow]")
        else:
            console.print("[yellow]Unknown choice. Use p, m, n, s, or q.[/yellow]")


def _append_review_record(
    records: list[dict[str, Any]],
    *,
    diarized_label: str,
    review_label: str,
    match: SpeakerMatch | None,
    result: _SpeakerReviewResult,
) -> None:
    records.append(
        _review_record_from_result(
            diarized_label=diarized_label,
            review_label=review_label,
            match=match,
            result=result,
        ),
    )


def _append_cached_skip_record(
    records: list[dict[str, Any]],
    *,
    diarized_label: str,
    review_label: str,
    match: SpeakerMatch | None,
    skipped_entry: dict[str, Any],
) -> None:
    _append_review_record(
        records,
        diarized_label=diarized_label,
        review_label=review_label,
        match=match,
        result=_SpeakerReviewResult(
            changed=False,
            action="skipped_cached",
            target_profile_id=str(skipped_entry.get("id")),
            target_display_name=str(skipped_entry.get("label")),
        ),
    )


def _append_short_skip_record(
    records: list[dict[str, Any]],
    *,
    diarized_label: str,
    review_label: str,
    match: SpeakerMatch | None,
) -> None:
    _append_review_record(
        records,
        diarized_label=diarized_label,
        review_label=review_label,
        match=match,
        result=_SpeakerReviewResult(changed=False, action="skipped_short"),
    )


def _append_no_embedding_skip_record(
    records: list[dict[str, Any]],
    *,
    diarized_label: str,
    review_label: str,
    match: SpeakerMatch | None,
) -> None:
    _append_review_record(
        records,
        diarized_label=diarized_label,
        review_label=review_label,
        match=match,
        result=_SpeakerReviewResult(changed=False, action="skipped_no_embedding"),
    )


def _print_no_review_summary(
    *,
    skipped_named: list[tuple[str, SpeakerMatch]],
    skipped_prior: list[str],
    skipped_short: list[str],
    skipped_no_embedding: list[str],
) -> None:
    console.print("[dim]No reviewable unknown speakers found in this audio.[/dim]")
    if skipped_named:
        console.print("[dim]Skipped named speaker matches:[/dim]")
        for label, match in skipped_named:
            console.print(
                f"[dim]  {label} -> {match.display_name} "
                f"({match.profile_id}, {match.similarity:.2f})[/dim]",
            )
    if skipped_prior:
        console.print("[dim]Skipped previously skipped speakers:[/dim]")
        for label in skipped_prior:
            console.print(f"[dim]  {label}[/dim]")
    if skipped_short:
        console.print("[dim]Skipped short speaker fragments:[/dim]")
        for label in skipped_short:
            console.print(f"[dim]  {label} (<{REVIEW_MIN_PROMPT_SEGMENT_SECONDS:.0f}s)[/dim]")
    if skipped_no_embedding:
        console.print("[dim]Skipped speakers without embeddings:[/dim]")
        for label in skipped_no_embedding:
            console.print(f"[dim]  {label}[/dim]")


def _review_unknown_speakers(
    *,
    audio_path: Path,
    segments: list[DiarizedSegment],
    embeddings: dict[str, list[float]],
    matches: dict[str, SpeakerMatch],
    store: dict[str, Any],
    review_state: dict[str, Any],
    speaker_match_threshold: float,
    snippet_seconds: float,
    player: str | None,
) -> tuple[bool, list[dict[str, Any]]]:
    changed = False
    records: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="agent-cli-speakers-") as temp_dir:
        snippet_dir = Path(temp_dir)
        reviewed_count = 0
        skipped_named: list[tuple[str, SpeakerMatch]] = []
        skipped_prior: list[str] = []
        skipped_short: list[str] = []
        skipped_no_embedding: list[str] = []
        for label in _speaker_labels_by_first_turn(segments):
            match = matches.get(label)
            if _is_named_review_match(store=store, match=match):
                assert match is not None
                skipped_named.append((label, match))
                continue
            embedding = embeddings.get(label)
            source_profile_id = _source_review_profile_id(store, match)
            review_label = _review_label(diarized_label=label, store=store, match=match)
            skipped_entry = _matching_skipped_speaker(
                review_state,
                source_profile_id=source_profile_id,
                embedding=embedding,
                threshold=speaker_match_threshold,
            )
            if skipped_entry is not None:
                skipped_prior.append(review_label)
                _append_cached_skip_record(
                    records,
                    diarized_label=label,
                    review_label=review_label,
                    match=match,
                    skipped_entry=skipped_entry,
                )
                continue
            segment = best_clean_speaker_segment(
                segments,
                label,
                neighbor_gap_seconds=REVIEW_SNIPPET_NEIGHBOR_GAP_SECONDS,
            )
            if segment is None:
                continue
            if segment.end - segment.start < REVIEW_MIN_PROMPT_SEGMENT_SECONDS:
                skipped_short.append(review_label)
                _append_short_skip_record(
                    records,
                    diarized_label=label,
                    review_label=review_label,
                    match=match,
                )
                continue
            if embedding is None and source_profile_id is None:
                skipped_no_embedding.append(review_label)
                _append_no_embedding_skip_record(
                    records,
                    diarized_label=label,
                    review_label=review_label,
                    match=match,
                )
                continue
            try:
                snippet_path = _write_speaker_snippet(
                    audio_path=audio_path,
                    segment=segment,
                    output_dir=snippet_dir,
                    seconds=snippet_seconds,
                )
            except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
                console.print(f"[yellow]Could not create snippet for {label}: {exc}[/yellow]")
                continue
            reviewed_count += 1
            try:
                result = _review_speaker(
                    label=review_label,
                    snippet_path=snippet_path,
                    embedding=embeddings.get(label),
                    match=match,
                    store=store,
                    player=player,
                )
                _append_review_record(
                    records,
                    diarized_label=label,
                    review_label=review_label,
                    match=match,
                    result=result,
                )
                if result.action == "skipped":
                    _record_skipped_speaker(
                        review_state,
                        review_label=review_label,
                        source_profile_id=source_profile_id,
                        embedding=embedding,
                    )
                changed = result.changed or changed
            except typer.Exit as exc:
                raise _ReviewInterruptedError(changed, records) from exc
        if reviewed_count == 0:
            _print_no_review_summary(
                skipped_named=skipped_named,
                skipped_prior=skipped_prior,
                skipped_short=skipped_short,
                skipped_no_embedding=skipped_no_embedding,
            )
    return changed, records


def _review_audio_targets(
    *,
    audio_targets: list[Path],
    review_state: dict[str, Any],
    store: dict[str, Any],
    diarizer: SpeakerDiarizer,
    hf_token: str,
    speaker_match_threshold: float,
    snippet_seconds: float,
    player: str | None,
    force_review: bool,
    review_state_path: Path,
) -> tuple[bool, int, int, bool]:
    changed = False
    reviewed_audio_count = 0
    skipped_audio_count = 0
    interrupted = False

    for audio_path in audio_targets:
        if not force_review and _audio_review_is_cached(review_state, audio_path):
            skipped_audio_count += 1
            continue

        console.print(f"[blue]Running diarization on {audio_path}...[/blue]")
        with _suppress_speaker_review_warnings():
            segments = diarizer.diarize(audio_path)
        if not segments:
            console.print("[yellow]Diarization returned no speaker segments.[/yellow]")
            _record_audio_review(review_state, audio_path, [])
            _save_review_state(review_state_path, review_state)
            reviewed_audio_count += 1
            continue

        with _suppress_speaker_review_warnings():
            embeddings = extract_speaker_embeddings(
                audio_path=audio_path,
                segments=segments,
                hf_token=hf_token,
                device=diarizer.device,
            )
        matches = match_speaker_profiles(
            embeddings,
            store,
            threshold=speaker_match_threshold,
        )

        try:
            audio_changed, records = _review_unknown_speakers(
                audio_path=audio_path,
                segments=segments,
                embeddings=embeddings,
                matches=matches,
                store=store,
                review_state=review_state,
                speaker_match_threshold=speaker_match_threshold,
                snippet_seconds=snippet_seconds,
                player=player,
            )
        except _ReviewInterruptedError as exc:
            audio_changed = exc.changed
            records = exc.records
            interrupted = True

        _record_audio_review(review_state, audio_path, records)
        _save_review_state(review_state_path, review_state)
        reviewed_audio_count += 1
        changed = audio_changed or changed

        if interrupted:
            break

    return changed, reviewed_audio_count, skipped_audio_count, interrupted


@speakers_app.command("list")
def list_speakers(
    speaker_profiles_file: Path = SPEAKER_PROFILES_FILE_OPTION,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output profile metadata as JSON without embedding vectors.",
        ),
    ] = False,
    _config_file: str | None = opts.CONFIG_FILE,
) -> None:
    """List stored diarization speaker profiles."""
    path = speaker_profiles_file.expanduser()
    store = _load_store_or_exit(path)
    profiles = summarize_speaker_profiles(store)

    if json_output:
        print(
            json.dumps(
                {
                    "speaker_profiles_file": str(path),
                    "profiles": profiles,
                },
            ),
        )
        return

    if not profiles:
        console.print(f"[dim]No speaker profiles found in {path}.[/dim]")
        return

    table = Table(title="Speaker Profiles")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Embeddings", justify="right")
    table.add_column("Updated", style="dim")

    for profile in profiles:
        table.add_row(
            str(profile["id"]),
            str(profile["name"] or ""),
            "unknown" if profile["anonymous"] else "named",
            str(profile["embedding_count"]),
            str(profile["updated_at"] or ""),
        )

    console.print(table)


@speakers_app.command("rename")
def rename_speaker(
    identifier: Annotated[
        str,
        typer.Argument(help="Existing profile id or name, e.g. UNKNOWN_001."),
    ],
    name: Annotated[
        str,
        typer.Argument(help='New display name, e.g. "John". Quote names with spaces.'),
    ],
    speaker_profiles_file: Path = SPEAKER_PROFILES_FILE_OPTION,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output the renamed profile metadata as JSON.",
        ),
    ] = False,
    _config_file: str | None = opts.CONFIG_FILE,
) -> None:
    """Rename a stored speaker profile without changing its embeddings."""
    path = speaker_profiles_file.expanduser()
    store = _load_store_or_exit(path)

    try:
        profile = rename_speaker_profile(store, identifier, name)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        if str(exc) == f"Another speaker profile already uses {name.strip()!r}.":
            command = _merge_command_hint(identifier, name.strip())
            console.print(
                "[yellow]That name is already a speaker profile. "
                "Merge embeddings instead with:[/yellow] "
                f"[bold]{escape(command)}[/bold]",
            )
        raise typer.Exit(1) from exc

    save_speaker_profile_store(path, store)
    summary = summarize_speaker_profile(profile)

    if json_output:
        print(
            json.dumps(
                {
                    "speaker_profiles_file": str(path),
                    "profile": summary,
                },
            ),
        )
        return

    console.print(
        f"[green]Renamed speaker[/green] [cyan]{summary['id']}[/cyan] "
        f"to [bold]{summary['display_name']}[/bold].",
    )


@speakers_app.command("merge")
def merge_speakers(
    source: Annotated[
        str,
        typer.Argument(help="Duplicate profile id or name to remove, e.g. UNKNOWN_002."),
    ],
    target: Annotated[
        str,
        typer.Argument(help="Profile id or name to keep, e.g. John or UNKNOWN_001."),
    ],
    speaker_profiles_file: Path = SPEAKER_PROFILES_FILE_OPTION,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output the merged target profile metadata as JSON.",
        ),
    ] = False,
    _config_file: str | None = opts.CONFIG_FILE,
) -> None:
    """Merge a duplicate speaker profile into the profile to keep."""
    path = speaker_profiles_file.expanduser()
    store = _load_store_or_exit(path)

    try:
        profile = merge_speaker_profiles(store, source, target)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    save_speaker_profile_store(path, store)
    summary = summarize_speaker_profile(profile)

    if json_output:
        print(
            json.dumps(
                {
                    "speaker_profiles_file": str(path),
                    "merged_source": source,
                    "profile": summary,
                },
            ),
        )
        return

    console.print(
        f"[green]Merged speaker[/green] [cyan]{source}[/cyan] into "
        f"[bold]{summary['display_name']}[/bold] ([cyan]{summary['id']}[/cyan]).",
    )


@speakers_app.command("review")
@requires_extras("diarization", process_name="speakers-review")
def review_speakers(
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file",
            help="Review speakers from an existing audio file.",
        ),
    ] = None,
    last_recording: Annotated[
        int | None,
        typer.Option(
            "--last-recording",
            help="Review the Nth most recent saved transcribe recording.",
        ),
    ] = None,
    last_session: Annotated[
        int | None,
        typer.Option(
            "--last-session",
            "--last-live-session",
            help=(
                "Review the Nth most recent inferred transcribe-live session "
                "(default source when available)."
            ),
        ),
    ] = None,
    session_gap: Annotated[
        float,
        typer.Option(
            "--session-gap",
            help="Maximum seconds between transcribe-live chunks in one session.",
        ),
    ] = 300.0,
    transcription_log: Path = REVIEW_TRANSCRIPTION_LOG_OPTION,
    hf_token: str | None = opts.HF_TOKEN,
    speakers: Annotated[
        int | None,
        typer.Option(
            "--speakers",
            help="Known number of speakers. Sets both --min-speakers and --max-speakers.",
        ),
    ] = None,
    min_speakers: int | None = opts.MIN_SPEAKERS,
    max_speakers: int | None = opts.MAX_SPEAKERS,
    speaker_profiles_file: Path = SPEAKER_PROFILES_FILE_OPTION,
    speaker_match_threshold: float = opts.SPEAKER_MATCH_THRESHOLD,
    snippet_seconds: Annotated[
        float,
        typer.Option(
            "--snippet-seconds",
            min=0.5,
            help="Maximum seconds to play for each speaker snippet.",
        ),
    ] = 6.0,
    player: Annotated[
        str | None,
        typer.Option(
            "--player",
            help="Audio player command to use for snippets (default: afplay, ffplay, aplay, or paplay).",
        ),
    ] = None,
    review_state_file: Path = REVIEW_STATE_FILE_OPTION,
    force_review: Annotated[
        bool,
        typer.Option(
            "--force-review",
            help="Review audio even if it is already present in the speaker review cache.",
        ),
    ] = False,
    _config_file: str | None = opts.CONFIG_FILE,
) -> None:
    """Interactively review diarized speakers by listening to snippets."""
    if speakers is not None and (min_speakers is not None or max_speakers is not None):
        console.print(
            "[red]Use either --speakers or --min-speakers/--max-speakers, not both.[/red]"
        )
        raise typer.Exit(1)
    if not hf_token:
        hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        console.print(
            "[red]--hf-token required for speaker review. "
            "Set HF_TOKEN env var or pass --hf-token.[/red]",
        )
        raise typer.Exit(1)

    try:
        audio_targets = _resolve_review_audio_targets(
            from_file=from_file,
            last_recording=last_recording,
            last_session=last_session,
            transcription_log=transcription_log,
            session_gap=session_gap,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    try:
        review_state_path = review_state_file.expanduser()
        review_state = _load_review_state(review_state_path)
    except (TypeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    with _suppress_speaker_review_warnings():
        diarizer = SpeakerDiarizer(
            hf_token=hf_token,
            min_speakers=speakers if speakers is not None else min_speakers,
            max_speakers=speakers if speakers is not None else max_speakers,
        )

    profiles_path = speaker_profiles_file.expanduser()
    store = _load_store_or_exit(profiles_path)
    changed, reviewed_audio_count, skipped_audio_count, interrupted = _review_audio_targets(
        audio_targets=audio_targets,
        review_state=review_state,
        store=store,
        diarizer=diarizer,
        hf_token=hf_token,
        speaker_match_threshold=speaker_match_threshold,
        snippet_seconds=snippet_seconds,
        player=player,
        force_review=force_review,
        review_state_path=review_state_path,
    )

    _save_review_state(review_state_path, review_state)

    if changed:
        save_speaker_profile_store(profiles_path, store)
        console.print(f"[green]Saved speaker profiles to {profiles_path}.[/green]")
    if reviewed_audio_count:
        console.print(f"[green]Saved speaker review state to {review_state_path}.[/green]")
    if interrupted:
        raise typer.Exit(0)

    if skipped_audio_count:
        console.print(f"[dim]Skipped {skipped_audio_count} already reviewed audio file(s).[/dim]")

    if changed:
        return
    if reviewed_audio_count:
        console.print("[dim]No speaker profile changes made.[/dim]")
    else:
        console.print("[dim]No unreviewed audio files found.[/dim]")
