"""Persistence logic for memory entries (File + Vector DB)."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent_cli.memory._files import (
    _DELETED_DIRNAME,
    _slugify,
    ensure_store_dirs,
    load_snapshot,
    read_memory_file,
    soft_delete_memory_file,
    write_memory_file,
    write_snapshot,
)
from agent_cli.memory._store import (
    delete_entries,
    delete_summaries,
    list_conversation_entries,
    upsert_memories,
    upsert_summary_entries,
)
from agent_cli.memory.entities import Fact, Turn
from agent_cli.memory.models import MemoryMetadata

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.summarizer import SummaryResult

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


def persist_hierarchical_summary(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    summary_result: SummaryResult,
) -> list[str]:
    """Persist a hierarchical summary to disk and ChromaDB.

    This function:
    1. Deletes existing summaries (files and ChromaDB entries)
    2. Writes new summary files to disk in hierarchical structure
    3. Stores entries in ChromaDB

    Args:
        collection: ChromaDB collection.
        memory_root: Root path for memory files.
        conversation_id: The conversation this summary belongs to.
        summary_result: The result from summarize().

    Returns:
        List of IDs that were stored.

    """
    from agent_cli.summarizer import SummaryLevel  # noqa: PLC0415

    # Skip if no summary needed
    if summary_result.level == SummaryLevel.NONE:
        return []

    # Delete existing summary files
    _delete_summary_files(memory_root, conversation_id)

    # Delete existing ChromaDB entries
    delete_summaries(collection, conversation_id)

    # Get storage metadata from SummaryResult
    entries = summary_result.to_storage_metadata(conversation_id)
    if not entries:
        return []

    stored_ids: list[str] = []
    created_at = datetime.now(UTC).isoformat()

    for entry in entries:
        meta_dict = entry["metadata"]
        # Build MemoryMetadata from the summary result's metadata dict
        metadata = MemoryMetadata(
            conversation_id=meta_dict["conversation_id"],
            role=meta_dict["role"],
            created_at=meta_dict.get("created_at", created_at),
            summary_kind="summary",
            level=meta_dict.get("level"),
            is_final=meta_dict.get("is_final"),
            chunk_index=meta_dict.get("chunk_index"),
            group_index=meta_dict.get("group_index"),
            input_tokens=meta_dict.get("input_tokens"),
            output_tokens=meta_dict.get("output_tokens"),
            compression_ratio=meta_dict.get("compression_ratio"),
            summary_level_name=meta_dict.get("summary_level_name"),
        )
        record = write_memory_file(
            memory_root,
            content=entry["content"],
            doc_id=entry["id"],
            metadata=metadata,
        )
        LOGGER.info("Persisted summary file: %s (level=%s)", record.path, meta_dict.get("level"))
        stored_ids.append(record.id)

    # Store in ChromaDB (reuse the entries we already built)
    upsert_summary_entries(collection, entries)

    return stored_ids


def _delete_summary_files(memory_root: Path, conversation_id: str) -> None:
    """Delete all summary files for a conversation."""
    entries_dir, _ = ensure_store_dirs(memory_root)
    safe_conversation = _slugify(conversation_id)
    summaries_dir = entries_dir / safe_conversation / "summaries"

    if summaries_dir.exists():
        # Move to deleted folder instead of hard delete
        deleted_dir = entries_dir / _DELETED_DIRNAME / safe_conversation / "summaries"
        deleted_dir.parent.mkdir(parents=True, exist_ok=True)

        # If deleted summaries already exist, remove them first
        if deleted_dir.exists():
            shutil.rmtree(deleted_dir)

        # Move current summaries to deleted
        shutil.move(str(summaries_dir), str(deleted_dir))
        LOGGER.info("Moved old summaries to deleted: %s", deleted_dir)
