"""Persistence logic for memory entries (File + Vector DB)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_cli.memory._files import (
    _DELETED_DIRNAME,
    ensure_store_dirs,
    load_snapshot,
    read_memory_file,
    soft_delete_memory_file,
    write_memory_file,
    write_snapshot,
)
from agent_cli.memory._store import delete_entries, list_conversation_entries, upsert_memories
from agent_cli.memory.entities import Fact, Summary, Turn

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.memory.models import MemoryMetadata

LOGGER = logging.getLogger(__name__)

_SUMMARY_DOC_ID_SUFFIX = "::summary"


def _safe_identifier(value: str) -> str:
    """File/ID safe token preserving readability."""
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in value)
    return safe or "entry"


def persist_entries(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    entries: list[Turn | Fact | None],
) -> None:
    """Persist a batch of entries to disk and Chroma."""
    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[MemoryMetadata] = []

    for item in entries:
        if item is None:
            continue

        if isinstance(item, Turn):
            role: str = item.role
            source_id = None
        elif isinstance(item, Fact):
            role = "memory"
            source_id = item.source_id
        else:
            LOGGER.warning("Unknown entity type in persist_entries: %s", type(item))
            continue

        record = write_memory_file(
            memory_root,
            conversation_id=conversation_id,
            role=role,
            created_at=item.created_at.isoformat(),
            content=item.content,
            doc_id=item.id,
            source_id=source_id,
        )
        LOGGER.info("Persisted memory file: %s", record.path)
        ids.append(record.id)
        contents.append(record.content)
        metadatas.append(record.metadata)

    if ids:
        upsert_memories(collection, ids=ids, contents=contents, metadatas=metadatas)


def persist_summary(
    collection: Collection,
    *,
    memory_root: Path,
    summary: Summary,
) -> None:
    """Persist a summary to disk and Chroma."""
    doc_id = _safe_identifier(f"{summary.conversation_id}{_SUMMARY_DOC_ID_SUFFIX}-summary")
    record = write_memory_file(
        memory_root,
        conversation_id=summary.conversation_id,
        role="summary",
        created_at=summary.created_at.isoformat(),
        content=summary.content,
        summary_kind="summary",
        doc_id=doc_id,
    )
    upsert_memories(
        collection,
        ids=[record.id],
        contents=[record.content],
        metadatas=[record.metadata],
    )


def delete_memory_files(
    memory_root: Path,
    conversation_id: str,
    ids: list[str],
    replacement_map: dict[str, str] | None = None,
) -> None:
    """Delete markdown files (move to tombstone) and snapshot entries matching the given ids."""
    if not ids:
        return

    entries_dir, snapshot_path = ensure_store_dirs(memory_root)
    # Ensure we use the correct base for relative paths in soft_delete
    base_entries_dir = entries_dir
    conv_dir = entries_dir / _safe_identifier(conversation_id)
    snapshot = load_snapshot(snapshot_path)
    replacements = replacement_map or {}

    removed_ids: set[str] = set()

    # Prefer precise paths from the snapshot.
    for doc_id in ids:
        rec = snapshot.get(doc_id)
        if rec:
            soft_delete_memory_file(
                rec.path,
                base_entries_dir,
                replaced_by=replacements.get(doc_id),
            )
            snapshot.pop(doc_id, None)
            removed_ids.add(doc_id)

    remaining = {doc_id for doc_id in ids if doc_id not in removed_ids}

    # Fallback: scan the conversation folder for anything not in the snapshot.
    if remaining and conv_dir.exists():
        for path in conv_dir.rglob("*.md"):
            if _DELETED_DIRNAME in path.parts:
                continue
            rec = read_memory_file(path)
            if rec and rec.id in remaining:
                soft_delete_memory_file(
                    path,
                    base_entries_dir,
                    replaced_by=replacements.get(rec.id),
                )
                snapshot.pop(rec.id, None)
                removed_ids.add(rec.id)
                remaining.remove(rec.id)
                if not remaining:
                    break

    if removed_ids:
        write_snapshot(snapshot_path, snapshot.values())


def evict_if_needed(
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    max_entries: int,
) -> None:
    """Evict oldest non-summary entries beyond the max budget."""
    if max_entries <= 0:
        return
    entries = list_conversation_entries(collection, conversation_id, include_summary=False)
    if len(entries) <= max_entries:
        return
    # Sort by created_at asc
    sorted_entries = sorted(
        entries,
        key=lambda e: e.metadata.created_at,
    )
    overflow = sorted_entries[:-max_entries]
    ids_to_remove = [e.id for e in overflow]
    delete_entries(collection, ids_to_remove)
    delete_memory_files(memory_root, conversation_id, ids_to_remove)
