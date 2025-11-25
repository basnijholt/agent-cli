"""Utility functions for RAG: Document loading and chunking."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
LOGGER = logging.getLogger(__name__)

# Files to read as plain text directly (fast path)
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".py",
    ".js",
    ".ts",
    ".yaml",
    ".yml",
    ".rs",
    ".go",
    ".c",
    ".cpp",
    ".h",
    ".sh",
    ".toml",
    ".rst",
    ".ini",
    ".cfg",
}

# Files to convert using MarkItDown (rich documents)
MARKITDOWN_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".csv",
    ".xml",
}

SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | MARKITDOWN_EXTENSIONS


def load_document_text(file_path: Path) -> str | None:
    """Load text from a file path."""
    suffix = file_path.suffix.lower()

    try:
        if suffix in TEXT_EXTENSIONS:
            return file_path.read_text(errors="ignore")

        if suffix in MARKITDOWN_EXTENSIONS:
            from markitdown import MarkItDown  # noqa: PLC0415

            md = MarkItDown()
            result = md.convert(str(file_path))
            return result.text_content

        return None  # Unsupported
    except Exception:
        LOGGER.exception("Failed to load %s", file_path)
        return None


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into fixed-size chunks with overlap.

    Used as fallback when text has no natural sentence boundaries (e.g., code).
    """
    assert overlap < chunk_size, f"overlap ({overlap}) must be < chunk_size ({chunk_size})"

    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def _flush_buffer(buffer: list[str], chunks: list[str]) -> None:
    """Flush accumulated sentences to chunks list."""
    if buffer:
        chunks.append(" ".join(buffer))


def _compute_overlap_buffer(sentences: list[str], max_overlap: int) -> tuple[list[str], int]:
    """Keep trailing sentences that fit within overlap limit."""
    buffer: list[str] = []
    size = 0
    for s in reversed(sentences):
        if size + len(s) > max_overlap:
            break
        buffer.append(s)
        size += len(s)
    return list(reversed(buffer)), size


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text into chunks, preferring sentence boundaries.

    Strategy:
    1. Split on sentence boundaries (.!?) when possible
    2. Fall back to character-based splitting for oversized content (e.g., code)
    3. Maintain overlap between chunks for context continuity
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # Oversized sentence: flush buffer and hard-split
        if sentence_len > chunk_size:
            _flush_buffer(current, chunks)
            current, current_size = [], 0
            chunks.extend(_hard_split(sentence, chunk_size, overlap))
            continue

        # Would exceed chunk_size: flush and start new chunk with overlap
        if current_size + sentence_len > chunk_size and current:
            _flush_buffer(current, chunks)
            current, current_size = _compute_overlap_buffer(current, overlap)

        current.append(sentence)
        current_size += sentence_len

    _flush_buffer(current, chunks)
    return chunks


def get_file_hash(file_path: Path) -> str:
    """Get hash of file content."""
    return hashlib.md5(file_path.read_bytes(), usedforsecurity=False).hexdigest()
