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


# Separators for recursive splitting, ordered by preference (most semantic first)
SEPARATORS = (
    "\n\n",  # Paragraphs / code blocks
    "\n",  # Lines
    ". ",  # Sentences
    ", ",  # Clauses
    " ",  # Words
    "",  # Characters (last resort)
)


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into fixed-size chunks with overlap.

    Used as last-resort fallback when no separators work.
    """
    if overlap >= chunk_size:
        msg = f"overlap ({overlap}) must be < chunk_size ({chunk_size})"
        raise ValueError(msg)

    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def _recursive_split(
    text: str,
    separators: tuple[str, ...],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Recursively split text using semantic separators.

    Tries each separator in order, splitting on the most semantically
    meaningful boundary that produces chunks within the size limit.
    """
    # Base case: text fits in a single chunk
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    # Try each separator in order
    for i, sep in enumerate(separators):
        # Last resort: character-level split
        if sep == "":
            return _hard_split(text, chunk_size, overlap)

        parts = text.split(sep)
        if len(parts) == 1:
            # Separator not found, try next
            continue

        # Accumulate parts into chunks
        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0

        for part in parts:
            part_size = len(part) + len(sep)  # Include separator in size calculation

            # Part alone exceeds chunk_size: recurse with finer separator
            if len(part) > chunk_size:
                # Flush current buffer first
                if current_parts:
                    chunks.append(sep.join(current_parts))
                    current_parts = []
                    current_size = 0
                # Recurse on oversized part
                chunks.extend(_recursive_split(part, separators[i + 1 :], chunk_size, overlap))
                continue

            # Adding part would exceed chunk_size: flush and handle overlap
            if current_size + part_size > chunk_size and current_parts:
                chunks.append(sep.join(current_parts))
                # Compute overlap: keep trailing parts that fit
                overlap_parts, overlap_size = _compute_overlap(current_parts, sep, overlap)
                current_parts = overlap_parts
                current_size = overlap_size

            current_parts.append(part)
            current_size += part_size

        # Flush remaining
        if current_parts:
            chunks.append(sep.join(current_parts))

        return chunks

    # Shouldn't reach here, but fallback to hard split
    return _hard_split(text, chunk_size, overlap)


def _compute_overlap(
    parts: list[str],
    sep: str,
    max_overlap: int,
) -> tuple[list[str], int]:
    """Keep trailing parts that fit within overlap limit."""
    result: list[str] = []
    size = 0
    sep_len = len(sep)

    for part in reversed(parts):
        part_size = len(part) + sep_len
        if size + part_size > max_overlap:
            break
        result.append(part)
        size += part_size

    return list(reversed(result)), size


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    r"""Split text into chunks using recursive semantic splitting.

    Strategy:
    1. Try to split on paragraph boundaries (\n\n) first
    2. Fall back to lines (\n), then sentences (. ), clauses (, ), words ( )
    3. Last resort: character-level splitting for content with no natural boundaries
    4. Maintain overlap between chunks for context continuity

    This approach works well for both prose and code, preserving semantic
    boundaries like function definitions, paragraphs, and code blocks.

    Args:
        text: The text to chunk.
        chunk_size: Maximum chunk size in characters (default 1200, ~300 words).
        overlap: Overlap between chunks in characters for context continuity.

    Returns:
        List of text chunks.

    """
    if not text or not text.strip():
        return []

    return _recursive_split(text.strip(), SEPARATORS, chunk_size, overlap)


def get_file_hash(file_path: Path) -> str:
    """Get hash of file content."""
    return hashlib.md5(file_path.read_bytes(), usedforsecurity=False).hexdigest()
