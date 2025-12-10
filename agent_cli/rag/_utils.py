"""Utility functions for RAG: Document loading and chunking."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
LOGGER = logging.getLogger(__name__)

# Non-hidden directories to ignore (hidden dirs already caught by startswith(".") check)
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        "venv",
        "env",
        "htmlcov",
        "node_modules",
        "build",
        "dist",
    },
)

# Non-hidden files to ignore (hidden files already caught by startswith(".") check)
DEFAULT_IGNORE_FILES: frozenset[str] = frozenset(
    {
        "Thumbs.db",
    },
)


def should_ignore_path(path: Path, base_folder: Path) -> bool:
    """Check if a path should be ignored during indexing.

    Ignores:
    - Any path component starting with '.' (hidden files/dirs)
    - Common development directories (__pycache__, node_modules, venv, etc.)
    - .egg-info directories
    - OS metadata files (Thumbs.db)

    Args:
        path: The file path to check.
        base_folder: The base folder for computing relative paths.

    Returns:
        True if the path should be ignored, False otherwise.

    """
    rel_parts = path.relative_to(base_folder).parts

    for part in rel_parts:
        # Hidden files/directories (starting with .)
        if part.startswith("."):
            return True
        # Common ignore directories
        if part in DEFAULT_IGNORE_DIRS:
            return True
        # .egg-info directories
        if part.endswith(".egg-info"):
            return True

    # Check specific file patterns
    return path.name in DEFAULT_IGNORE_FILES


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


# Separators ordered by preference (most semantic first)
SEPARATORS = ("\n\n", "\n", ". ", ", ", " ")


def _find_break_point(text: str, start: int, end: int, min_chunk: int) -> int:
    """Find a good break point near end, preferring semantic boundaries.

    Searches backwards from end to find the last occurrence of a separator.
    Only accepts separators that would create a chunk of at least min_chunk size.
    If none qualify, falls back to the best available earlier separator before
    finally splitting at the exact end. Returns the position after the separator
    (so the separator stays with the preceding chunk).
    """
    min_pos = start + min_chunk
    fallback_point = -1
    for sep in SEPARATORS:
        pos = text.rfind(sep, start, end)
        if pos <= start:
            continue
        candidate = pos + len(sep)
        if pos >= min_pos:
            return candidate
        fallback_point = max(fallback_point, candidate)
    if fallback_point != -1:
        return fallback_point
    # No separator found at acceptable position, break at end (character-level split)
    return end


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    r"""Split text into chunks, preferring semantic boundaries.

    Strategy:
    1. Slice the original text directly (no split/join, so no char loss)
    2. Find break points at separators: \n\n, \n, ". ", ", ", " "
    3. Fall back to character-level breaks when no separator found
    4. Overlap by starting next chunk earlier in the text

    Args:
        text: The text to chunk.
        chunk_size: Maximum chunk size in characters (default 1200, ~300 words).
        overlap: Overlap between chunks in characters for context continuity.

    Returns:
        List of text chunks.

    Raises:
        ValueError: If chunk_size <= 0 or overlap >= chunk_size.

    """
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)
    if overlap >= chunk_size:
        msg = f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        raise ValueError(msg)

    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    # Only accept separators that use at least half the chunk budget
    min_chunk = chunk_size // 2

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # Last chunk - take everything remaining
            chunks.append(text[start:])
            break

        # Find a good break point
        break_point = _find_break_point(text, start, end, min_chunk)
        chunks.append(text[start:break_point])

        # Next chunk starts with overlap (but must make progress)
        start = max(start + 1, break_point - overlap)

    return chunks


def get_file_hash(file_path: Path) -> str:
    """Get hash of file content."""
    return hashlib.md5(file_path.read_bytes(), usedforsecurity=False).hexdigest()
