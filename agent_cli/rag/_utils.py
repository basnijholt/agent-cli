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


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text into chunks with overlap."""
    # Split by sentence boundaries mostly, avoiding split mid-sentence if possible
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks = []
    current: list[str] = []
    current_size = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If a single sentence is too big, we might have to split it hard (fallback)
        if sentence_len > chunk_size:
            # If we have accumulated content, flush it first
            if current:
                chunks.append(" ".join(current))
                current = []
                current_size = 0
            chunks.append(sentence)  # Add the long sentence as is (or could split further)
            continue

        if current_size + sentence_len > chunk_size and current:
            chunks.append(" ".join(current))

            # Calculate overlap: keep last few sentences that fit within overlap limit
            overlap_buffer: list[str] = []
            overlap_size = 0
            for s in reversed(current):
                if overlap_size + len(s) <= overlap:
                    overlap_buffer.append(s)
                    overlap_size += len(s)
                else:
                    break

            current = list(reversed(overlap_buffer))
            current_size = overlap_size

        current.append(sentence)
        current_size += sentence_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def get_file_hash(file_path: Path) -> str:
    """Get hash of file content."""
    return hashlib.md5(file_path.read_bytes(), usedforsecurity=False).hexdigest()
