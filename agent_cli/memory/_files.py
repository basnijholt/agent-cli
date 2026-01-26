"""File-backed memory helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import ValidationError

from agent_cli.core.utils import atomic_write_text
from agent_cli.memory.models import MemoryMetadata

if TYPE_CHECKING:
    from collections.abc import Iterable

LOGGER = logging.getLogger(__name__)

_ENTRIES_DIRNAME = "entries"
_SNAPSHOT_FILENAME = "memory_index.json"
_DELETED_DIRNAME = "deleted"


@dataclass
class MemoryFileRecord:
    """Materialized memory file on disk."""

    id: str
    path: Path
    metadata: MemoryMetadata
    content: str


def ensure_store_dirs(root: Path) -> tuple[Path, Path]:
    """Ensure base folders exist and return (entries_dir, snapshot_path)."""
    entries_dir = root / _ENTRIES_DIRNAME
    entries_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = root / _SNAPSHOT_FILENAME
    return entries_dir, snapshot_path


def _safe_timestamp(value: str) -> str:
    """Return a filesystem-safe timestamp-ish token."""
    return "".join(ch if ch.isalnum() or ch in "-._" else "-" for ch in value) or "ts"


def soft_delete_memory_file(
    path: Path,
    entries_dir: Path,
    replaced_by: str | None = None,
) -> None:
    """Move a memory file to the deleted directory, updating metadata if replaced."""
    try:
        rel_path = path.relative_to(entries_dir)
    except ValueError:
        # Not in entries_dir? Just unlink.
        path.unlink(missing_ok=True)
        return

    # Prepare destination
    dest_path = entries_dir / _DELETED_DIRNAME / rel_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # If we need to update metadata, read-modify-write
    if replaced_by:
        record = read_memory_file(path)
        if record:
            record.metadata.replaced_by = replaced_by
            front_matter = _render_front_matter(record.id, record.metadata)
            body = front_matter + "\n" + record.content + "\n"
            atomic_write_text(dest_path, body)
            path.unlink(missing_ok=True)
            return

    # Simple move if no metadata change
    path.rename(dest_path)


def write_memory_file(
    root: Path,
    *,
    conversation_id: str,
    role: str,
    created_at: str,
    content: str,
    summary_kind: str | None = None,
    doc_id: str | None = None,
    source_id: str | None = None,
) -> MemoryFileRecord:
    """Render and persist a memory document to disk."""
    entries_dir, _ = ensure_store_dirs(root)
    safe_conversation = _slugify(conversation_id)
    doc_id = doc_id or str(uuid4())
    safe_ts = _safe_timestamp(created_at)

    # Route by role/category for readability
    if summary_kind:
        subdir = Path("summaries")
        filename = "summary.md"
    elif role == "user":
        subdir = Path("turns") / "user"
        filename = f"{safe_ts}__{doc_id}.md"
    elif role == "assistant":
        subdir = Path("turns") / "assistant"
        filename = f"{safe_ts}__{doc_id}.md"
    elif role == "memory":
        subdir = Path("facts")
        filename = f"{safe_ts}__{doc_id}.md"
    else:
        subdir = Path()
        filename = f"{doc_id}.md"

    metadata = MemoryMetadata(
        conversation_id=conversation_id,
        role=role,
        created_at=created_at,
        summary_kind=summary_kind,
        source_id=source_id,
    )

    front_matter = _render_front_matter(doc_id, metadata)
    body = front_matter + "\n" + content.strip() + "\n"

    file_path = entries_dir / safe_conversation / subdir / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)

    atomic_write_text(file_path, body)

    return MemoryFileRecord(id=doc_id, path=file_path, metadata=metadata, content=content)


def load_memory_files(root: Path) -> list[MemoryFileRecord]:
    """Load all memory files from disk."""
    entries_dir, _ = ensure_store_dirs(root)
    records: list[MemoryFileRecord] = []
    for path in entries_dir.rglob("*.md"):
        # Skip anything under a deleted tombstone folder.
        if _DELETED_DIRNAME in path.parts:
            continue
        rec = read_memory_file(path)
        if rec:
            records.append(rec)
    return records


def read_memory_file(path: Path) -> MemoryFileRecord | None:
    """Parse a single memory file; return None if invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        LOGGER.warning("Failed to read memory file %s", path, exc_info=True)
        return None

    fm, body = _split_front_matter(text)
    if fm is None:
        LOGGER.warning("Memory file %s missing front matter; skipping", path)
        return None

    doc_id = fm.pop("id", None)
    if not doc_id:
        LOGGER.warning("Memory file %s missing id; skipping", path)
        return None

    try:
        metadata = MemoryMetadata(**fm)
    except ValidationError:
        LOGGER.warning("Memory file %s has invalid metadata; skipping", path, exc_info=True)
        return None

    return MemoryFileRecord(id=str(doc_id), path=path, metadata=metadata, content=body.strip())


def write_snapshot(snapshot_path: Path, records: Iterable[MemoryFileRecord]) -> None:
    """Write a JSON snapshot of current memories for easy inspection."""
    payload = [
        {
            "id": rec.id,
            "path": str(rec.path),
            "metadata": rec.metadata.model_dump(exclude_none=True),
            "content": rec.content,
        }
        for rec in records
    ]

    atomic_write_text(snapshot_path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_snapshot(snapshot_path: Path) -> dict[str, MemoryFileRecord]:
    """Load snapshot into a mapping from id to record (if the snapshot exists)."""
    if not snapshot_path.exists():
        return {}
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        LOGGER.warning("Failed to read memory snapshot %s", snapshot_path, exc_info=True)
        return {}

    records: dict[str, MemoryFileRecord] = {}
    for item in data:
        try:
            metadata = MemoryMetadata(**item["metadata"])
            record = MemoryFileRecord(
                id=str(item["id"]),
                path=Path(item["path"]),
                metadata=metadata,
                content=str(item.get("content") or ""),
            )
            records[record.id] = record
        except Exception:
            LOGGER.warning("Invalid snapshot entry; skipping", exc_info=True)
            continue
    return records


def _render_front_matter(doc_id: str, metadata: MemoryMetadata) -> str:
    """Return YAML front matter string."""
    import yaml  # noqa: PLC0415

    meta_dict = metadata.model_dump(exclude_none=True)
    meta_dict = {"id": doc_id, **meta_dict}
    yaml_block = yaml.safe_dump(meta_dict, sort_keys=False)
    return f"---\n{yaml_block}---"


def _split_front_matter(text: str) -> tuple[dict | None, str]:
    """Split YAML front matter from body."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    yaml_part = text[3:end]
    try:
        import yaml  # noqa: PLC0415

        meta = yaml.safe_load(yaml_part) or {}
    except Exception:
        return None, text
    body_start = end + len("\n---")
    body = text[body_start:].lstrip("\n")
    return meta, body


def _slugify(value: str) -> str:
    """Filesystem-safe slug for folder names."""
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in value)
    return safe or "default"
