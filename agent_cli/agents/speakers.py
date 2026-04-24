"""Manage persistent diarization speaker profiles."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003
from typing import Annotated, Any

import typer
from rich.table import Table

from agent_cli.cli import app
from agent_cli.core.process import set_process_title
from agent_cli.core.speaker_identity import (
    DEFAULT_SPEAKER_PROFILES_FILE,
    load_speaker_profile_store,
    merge_speaker_profiles,
    rename_speaker_profile,
    save_speaker_profile_store,
    summarize_speaker_profile,
    summarize_speaker_profiles,
)
from agent_cli.core.utils import console

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
