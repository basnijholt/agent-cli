"""Add memories directly to the memory store without LLM extraction."""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

import typer

from agent_cli import opts
from agent_cli.agents.memory import memory_app
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import console, print_command_line_args

if TYPE_CHECKING:
    from agent_cli.memory._files import MemoryFileRecord

# Matches markdown list prefixes: "- ", "* ", "+ ", "1. ", "2. ", etc.
_LIST_PREFIX_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")


def _strip_list_prefix(line: str) -> str:
    """Strip markdown/text list prefixes from a line."""
    return _LIST_PREFIX_RE.sub("", line)


def _parse_json_items(
    items: list[str | dict[str, Any]],
    default_conversation_id: str,
) -> list[tuple[str, str]]:
    """Parse a JSON list of items into (content, conversation_id) tuples."""
    results: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, str):
            results.append((item, default_conversation_id))
        else:
            results.append((item["content"], item.get("conversation_id", default_conversation_id)))
    return results


def _parse_memories(
    memories: list[str],
    file: Path | None,
    default_conversation_id: str,
) -> list[tuple[str, str]]:
    """Parse memories from arguments, file, or stdin."""
    results: list[tuple[str, str]] = []

    if file:
        text = sys.stdin.read() if str(file) == "-" else file.read_text()
        text = text.strip()

        parsed_json = False
        if text.startswith(("[", "{")):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    results.extend(_parse_json_items(data, default_conversation_id))
                    parsed_json = True
                elif isinstance(data, dict) and "memories" in data:
                    results.extend(_parse_json_items(data["memories"], default_conversation_id))
                    parsed_json = True
            except json.JSONDecodeError:
                pass  # Fall through to plain text parsing

        if not parsed_json:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    content = _strip_list_prefix(stripped)
                    if content:
                        results.append((content, default_conversation_id))

    results.extend((m, default_conversation_id) for m in memories)
    return results


def _write_memories(
    memory_path: Path,
    memories: list[tuple[str, str]],
    git_versioning: bool,
) -> list[MemoryFileRecord]:
    """Write memories to disk and optionally commit to git."""
    import asyncio  # noqa: PLC0415

    from agent_cli.memory._files import write_memory_file  # noqa: PLC0415
    from agent_cli.memory._git import commit_changes, init_repo  # noqa: PLC0415

    if git_versioning:
        init_repo(memory_path)

    records = []
    for content, conversation_id in memories:
        record = write_memory_file(
            memory_path,
            conversation_id=conversation_id,
            role="memory",
            created_at=datetime.now(tz=UTC).isoformat(),
            content=content,
        )
        records.append(record)

    if git_versioning and records:
        asyncio.run(commit_changes(memory_path, f"Add {len(records)} memories directly"))

    return records


@memory_app.command("add")
@requires_extras("memory")
def add(
    memories: list[str] = typer.Argument(  # noqa: B008
        None,
        help="Memories to add. Each argument becomes one fact.",
    ),
    file: Path | None = typer.Option(  # noqa: B008
        None,
        "--file",
        "-f",
        help="Read memories from file. Use '-' for stdin. Supports JSON array, JSON object with 'memories' key, or plain text (one per line).",
    ),
    conversation_id: str = typer.Option(
        "default",
        "--conversation-id",
        "-c",
        help="Conversation namespace for these memories. Memories are retrieved per-conversation unless shared globally.",
    ),
    memory_path: Path = typer.Option(  # noqa: B008
        "./memory_db",
        "--memory-path",
        help="Directory for memory storage (same as `memory proxy --memory-path`).",
    ),
    git_versioning: bool = typer.Option(
        True,  # noqa: FBT003
        "--git-versioning/--no-git-versioning",
        help="Auto-commit changes to git for version history.",
    ),
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Add memories directly without LLM extraction.

    This writes facts directly to the memory store, bypassing the LLM-based
    fact extraction. Useful for bulk imports or seeding memories.

    The memory proxy file watcher (if running) will auto-index new files.
    Otherwise, they'll be indexed on next memory proxy startup.

    Examples::

        # Add single memories as arguments
        agent-cli memory add "User likes coffee" "User lives in Amsterdam"

        # Read from JSON file
        agent-cli memory add -f memories.json

        # Read from stdin (plain text, one per line)
        echo "User prefers dark mode" | agent-cli memory add -f -

        # Read JSON from stdin
        echo '["Fact one", "Fact two"]' | agent-cli memory add -f -

        # Specify conversation ID
        agent-cli memory add -c work "Project deadline is Friday"

    """
    if print_args:
        print_command_line_args(locals())

    parsed = _parse_memories(memories or [], file, conversation_id)

    if not parsed:
        console.print("[red]No memories provided. Use arguments or --file.[/red]")
        raise typer.Exit(1)

    memory_path = memory_path.resolve()
    records = _write_memories(memory_path, parsed, git_versioning)

    if not quiet:
        console.print(f"[green]Added {len(records)} memories to {memory_path}[/green]")
        max_preview = 60
        for record in records:
            preview = record.content[:max_preview]
            ellipsis = "..." if len(record.content) > max_preview else ""
            console.print(f"  - [dim]{preview}{ellipsis}[/dim]")
