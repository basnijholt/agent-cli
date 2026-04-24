"""Manage persistent diarization speaker profiles."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any

import typer
from rich.markup import escape
from rich.table import Table

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.deps import requires_extras
from agent_cli.core.diarization import DiarizedSegment, SpeakerDiarizer
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
REVIEW_OUTPUT_DIR = Path.home() / ".cache" / "agent-cli" / "speaker-review"
DEFAULT_REVIEW_TRANSCRIPTION_LOG = Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"
REVIEW_TRANSCRIPTION_LOG_OPTION: Path = typer.Option(
    DEFAULT_REVIEW_TRANSCRIPTION_LOG,
    "--transcription-log",
    help="Path to the transcribe-live JSONL log for --last-session.",
)
REVIEW_OUTPUT_DIR_OPTION: Path = typer.Option(
    REVIEW_OUTPUT_DIR,
    "--output-dir",
    help="Directory for combined live-session audio and temporary snippets.",
)


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


def _combine_live_review_session(
    *,
    last_session: int,
    transcription_log: Path,
    output_dir: Path,
    session_gap: float,
) -> Path:
    """Combine a transcribe-live session into one reviewable WAV file."""
    from agent_cli.agents.diarize_live_session import (  # noqa: PLC0415
        combine_segments,
        load_segments,
        select_recent_session,
        session_basename,
        write_ffconcat_manifest,
    )

    log_path = transcription_log.expanduser()
    if not log_path.exists():
        msg = f"Transcription log not found: {log_path}"
        raise FileNotFoundError(msg)
    selected = select_recent_session(
        load_segments(log_path),
        index=last_session,
        max_gap_seconds=session_gap,
    )
    missing = [segment.audio_file for segment in selected if not segment.audio_file.exists()]
    if missing:
        missing_list = "\n".join(str(path) for path in missing)
        msg = f"Selected audio files are missing:\n{missing_list}"
        raise FileNotFoundError(msg)

    output_dir = output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    basename = session_basename(selected)
    manifest_path = output_dir / f"{basename}.ffconcat"
    combined_audio = output_dir / f"{basename}.wav"
    write_ffconcat_manifest(selected, manifest_path)
    combine_segments(manifest_path, combined_audio)
    return combined_audio


def _resolve_review_audio_source(
    *,
    from_file: Path | None,
    last_recording: int | None,
    last_session: int | None,
    transcription_log: Path,
    output_dir: Path,
    session_gap: float,
) -> Path:
    """Resolve the audio file that should be reviewed."""
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
        return path

    if last_session is not None:
        if last_session < 1:
            msg = "--last-session must be 1 or greater."
            raise ValueError(msg)
        return _combine_live_review_session(
            last_session=last_session,
            transcription_log=transcription_log,
            output_dir=output_dir,
            session_gap=session_gap,
        )

    recording_index = last_recording or 1
    if recording_index < 1:
        msg = "--last-recording must be 1 or greater."
        raise ValueError(msg)
    recording = get_last_recording(recording_index)
    if recording is None:
        msg = f"Recording #{recording_index} not found."
        raise FileNotFoundError(msg)
    return recording


def _speaker_labels_by_first_turn(segments: list[DiarizedSegment]) -> list[str]:
    first_seen: dict[str, float] = {}
    for segment in segments:
        first_seen.setdefault(segment.speaker, segment.start)
    return [label for label, _ in sorted(first_seen.items(), key=lambda item: item[1])]


def _best_segment_for_speaker(
    segments: list[DiarizedSegment],
    speaker: str,
) -> DiarizedSegment | None:
    candidates = [
        segment
        for segment in segments
        if segment.speaker == speaker and segment.end > segment.start
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda segment: segment.end - segment.start)


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
        return [*shlex.split(player), str(audio_path)]
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", str(audio_path)]
    if shutil.which("ffplay"):
        return ["ffplay", "-autoexit", "-nodisp", "-loglevel", "error", str(audio_path)]
    if shutil.which("aplay"):
        return ["aplay", str(audio_path)]
    if shutil.which("paplay"):
        return ["paplay", str(audio_path)]
    msg = "No audio player found. Install ffmpeg/ffplay or pass --player."
    raise RuntimeError(msg)


def _play_audio_file(audio_path: Path, *, player: str | None = None) -> None:
    """Play an audio file with a local command-line player."""
    subprocess.run(_audio_player_command(player, audio_path), check=True)


def _review_choice_prompt() -> str:
    return (
        typer.prompt(
            "Action [p] replay, [m] merge, [n] new, [s] skip, [q] quit",
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
) -> None:
    console.print(f"\n[bold]Speaker:[/bold] [cyan]{label}[/cyan]")
    if match is not None:
        console.print(
            "[dim]Closest profile:[/dim] "
            f"[bold]{match.display_name}[/bold] "
            f"([cyan]{match.profile_id}[/cyan], {match.similarity:.2f})",
        )
    if embedding is None:
        console.print(
            "[yellow]No embedding was available for this speaker; only skip/replay works.[/yellow]"
        )


def _play_review_snippet(snippet_path: Path, *, player: str | None) -> None:
    try:
        _play_audio_file(snippet_path, player=player)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        console.print(f"[yellow]Could not play snippet: {exc}[/yellow]")


def _merge_review_speaker(
    *,
    label: str,
    embedding: list[float],
    match: SpeakerMatch | None,
    store: dict[str, Any],
) -> bool:
    if match is not None:
        target = typer.prompt("Target profile id/name", default=match.display_name).strip()
    else:
        target = typer.prompt("Target profile id/name").strip()
    try:
        profile = add_speaker_embedding_to_profile(store, target, embedding)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return False
    summary = summarize_speaker_profile(profile)
    console.print(
        f"[green]Merged current speaker {label} into {summary['display_name']}.[/green]",
    )
    return True


def _create_review_speaker(
    *,
    embedding: list[float],
    store: dict[str, Any],
) -> bool:
    name = typer.prompt("New speaker name").strip()
    try:
        profile = create_speaker_profile_from_embedding(store, name, embedding)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return False
    summary = summarize_speaker_profile(profile)
    console.print(f"[green]Created speaker profile {summary['display_name']}.[/green]")
    return True


def _review_speaker(
    *,
    label: str,
    snippet_path: Path,
    embedding: list[float] | None,
    match: SpeakerMatch | None,
    store: dict[str, Any],
    player: str | None,
) -> bool:
    """Interactively review one diarized speaker label."""
    changed = False
    while True:
        _print_review_speaker_intro(label=label, embedding=embedding, match=match)
        _play_review_snippet(snippet_path, player=player)

        choice = _review_choice_prompt()
        if choice in {"p", "play", "replay"}:
            continue
        if choice in {"s", "skip", ""}:
            console.print(f"[dim]Skipped {label}.[/dim]")
            return changed
        if choice in {"q", "quit"}:
            raise typer.Exit(0)
        if embedding is None:
            console.print("[yellow]Choose skip or replay; this speaker has no embedding.[/yellow]")
            continue
        if choice in {"m", "merge"}:
            changed = _merge_review_speaker(
                label=label, embedding=embedding, match=match, store=store
            )
            if changed:
                return True
            continue
        if choice in {"n", "new", "name"}:
            changed = _create_review_speaker(embedding=embedding, store=store)
            if changed:
                return True
            continue
        console.print("[yellow]Unknown choice. Use p, m, n, s, or q.[/yellow]")


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
            help="Review the Nth most recent saved transcribe recording (default: 1).",
        ),
    ] = None,
    last_session: Annotated[
        int | None,
        typer.Option(
            "--last-session",
            help="Review the Nth most recent inferred transcribe-live session.",
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
    output_dir: Path = REVIEW_OUTPUT_DIR_OPTION,
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
        audio_path = _resolve_review_audio_source(
            from_file=from_file,
            last_recording=last_recording,
            last_session=last_session,
            transcription_log=transcription_log,
            output_dir=output_dir,
            session_gap=session_gap,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    diarizer = SpeakerDiarizer(
        hf_token=hf_token,
        min_speakers=speakers if speakers is not None else min_speakers,
        max_speakers=speakers if speakers is not None else max_speakers,
    )
    console.print(f"[blue]Running diarization on {audio_path}...[/blue]")
    segments = diarizer.diarize(audio_path)
    if not segments:
        console.print("[red]Diarization returned no speaker segments.[/red]")
        raise typer.Exit(1)

    profiles_path = speaker_profiles_file.expanduser()
    store = _load_store_or_exit(profiles_path)
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

    changed = False
    with TemporaryDirectory(prefix="agent-cli-speakers-") as temp_dir:
        snippet_dir = Path(temp_dir)
        for label in _speaker_labels_by_first_turn(segments):
            segment = _best_segment_for_speaker(segments, label)
            if segment is None:
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
            changed = (
                _review_speaker(
                    label=label,
                    snippet_path=snippet_path,
                    embedding=embeddings.get(label),
                    match=matches.get(label),
                    store=store,
                    player=player,
                )
                or changed
            )

    if changed:
        save_speaker_profile_store(profiles_path, store)
        console.print(f"[green]Saved speaker profiles to {profiles_path}.[/green]")
    else:
        console.print("[dim]No speaker profile changes made.[/dim]")
