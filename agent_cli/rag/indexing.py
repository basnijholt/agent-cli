"""RAG Indexing Logic."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from agent_cli.rag.store import (
    delete_by_file_path,
    get_all_metadata,
    upsert_docs,
)
from agent_cli.rag.utils import chunk_text, get_file_hash, load_document_text

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

logger = logging.getLogger("agent_cli.rag.indexing")


def load_hashes_from_metadata(collection: Collection) -> dict[str, str]:
    """Rebuild hash cache from existing DB."""
    hashes = {}
    try:
        metadatas = get_all_metadata(collection)
        for meta in metadatas:
            if meta and "file_path" in meta and "file_hash" in meta:
                hashes[str(meta["file_path"])] = str(meta["file_hash"])
    except Exception:
        logger.warning("Could not load existing hashes", exc_info=True)
    return hashes


def index_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
) -> bool:
    """Index or reindex a single file.

    Returns:
        True if the file was indexed (changed or new), False otherwise.

    """
    if not file_path.exists():
        return False

    try:
        # Check if file changed
        current_hash = get_file_hash(file_path)

        # Handle relative path safely
        try:
            relative_path = str(file_path.relative_to(docs_folder))
        except ValueError:
            # Fallback if not relative (e.g. symlink or misconfiguration)
            relative_path = file_path.name

        if relative_path in file_hashes and file_hashes[relative_path] == current_hash:
            return False  # No change, skip

        # Remove old chunks first (atomic-ish update)
        remove_file(collection, docs_folder, file_path, file_hashes)

        # Load document
        text = load_document_text(file_path)
        if not text or not text.strip():
            return False  # Unsupported or empty

        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            return False

        # Index chunks
        ids = []
        documents = []
        metadatas = []

        timestamp = datetime.datetime.now(datetime.UTC).isoformat()

        for i, chunk in enumerate(chunks):
            doc_id = f"{relative_path}:chunk:{i}"
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "source": file_path.name,
                    "file_path": relative_path,
                    "file_type": file_path.suffix,
                    "chunk_id": i,
                    "total_chunks": len(chunks),
                    "indexed_at": timestamp,
                    "file_hash": current_hash,
                },
            )

        # Upsert to ChromaDB in batches to avoid 502s from large payloads
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]
            upsert_docs(collection, batch_ids, batch_docs, batch_meta)

        # Update hash tracking
        file_hashes[relative_path] = current_hash

        logger.info("  ✓ Indexed %s: %d chunks", file_path.name, len(chunks))
        return True

    except Exception:
        logger.exception("Failed to index file %s", file_path)
        return False


def remove_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
) -> bool:
    """Remove all chunks of a file from index.

    Returns:
        True if documents were removed, False otherwise.

    """
    try:
        try:
            relative_path = str(file_path.relative_to(docs_folder))
        except ValueError:
            relative_path = file_path.name

        count = delete_by_file_path(collection, relative_path)
        if count > 0:
            logger.info("  ✓ Removed %d chunks for %s", count, file_path.name)
            # Remove from hash tracking
            file_hashes.pop(relative_path, None)
            return True

        # Still remove from hash tracking if it exists there but not in DB (edge case)
        if relative_path in file_hashes:
            file_hashes.pop(relative_path, None)

        return False
    except Exception:
        logger.exception("Error removing file %s", file_path)
        return False


def initial_index(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> None:
    """Index all existing files on startup and remove deleted ones."""
    logger.info("🔍 Scanning existing files...")

    # Snapshot of what's in the DB currently
    paths_in_db = set(file_hashes.keys())
    paths_found_on_disk = set()

    processed_files = []
    removed_files = []

    # 1. Index Existing Files
    for file_path in docs_folder.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            try:
                # Track that we found this file
                try:
                    rel_path = str(file_path.relative_to(docs_folder))
                    paths_found_on_disk.add(rel_path)
                except ValueError:
                    pass

                if index_file(collection, docs_folder, file_path, file_hashes):
                    processed_files.append(file_path.name)

            except Exception:
                logger.exception("Error processing %s", file_path.name)

    # 2. Clean up Deleted Files
    # If it's in DB but not found on disk, it was deleted offline.
    paths_to_remove = paths_in_db - paths_found_on_disk

    if paths_to_remove:
        logger.info("🧹 Cleaning up %d deleted files found in index...", len(paths_to_remove))
        for rel_path in paths_to_remove:
            full_path = docs_folder / rel_path
            try:
                if remove_file(collection, docs_folder, full_path, file_hashes):
                    removed_files.append(rel_path)
            except Exception:
                logger.exception("Error removing stale file %s", rel_path)

    if processed_files:
        logger.info("🆕 Added/Updated: %s", ", ".join(processed_files))

    if removed_files:
        logger.info("🗑️ Removed: %s", ", ".join(removed_files))

    logger.info(
        "✅ Initial scan complete. Indexed/Checked %d files, Removed %d stale files.",
        len(paths_found_on_disk),
        len(removed_files),
    )
