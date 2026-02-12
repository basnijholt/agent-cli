"""Utility functions for RAG: Document loading and chunking."""

from __future__ import annotations

import fnmatch
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


def _parse_gitignore(gitignore_path: Path) -> list[str]:
    """Parse a .gitignore file and return a list of patterns."""
    try:
        text = gitignore_path.read_text(errors="ignore")
    except OSError:
        return []
    patterns = []
    for line in text.splitlines():
        line = line.strip()  # noqa: PLW2901
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _gitignore_pattern_matches(pattern: str, rel_path_str: str, is_dir: bool) -> bool:
    """Check if a single gitignore pattern matches a relative path.

    Supports:
    - Simple filename patterns (e.g. ``*.log``)
    - Directory-only patterns with trailing ``/`` (e.g. ``build/``)
    - Rooted patterns with leading ``/`` (e.g. ``/dist``)
    - Patterns with ``/`` that match against the full path
    - ``**`` for matching across directories
    """
    # Directory-only pattern (trailing /)
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    # Rooted pattern (leading /)
    rooted = pattern.startswith("/")
    if rooted:
        pattern = pattern.lstrip("/")

    # Convert ** to fnmatch-compatible pattern
    # "**/" matches any number of directories
    glob_pattern = pattern.replace("**/", "__GLOBSTAR__/")
    glob_pattern = glob_pattern.replace("/**", "/__GLOBSTAR__")
    glob_pattern = glob_pattern.replace("**", "__GLOBSTAR__")

    # For patterns without /, match against any path component (unless rooted)
    if "/" not in pattern and not rooted:
        # Simple pattern like "*.log" or "build" — match against each component
        parts = rel_path_str.split("/")
        # For dir-only patterns, only match directory components (all except last for files)
        components_to_check = (parts[:-1] if not is_dir else parts) if dir_only else parts
        return any(fnmatch.fnmatch(part, pattern) for part in components_to_check)

    # Pattern contains / — match against full relative path
    # Restore ** handling
    glob_pattern = glob_pattern.replace("__GLOBSTAR__", "*")

    if rooted:
        # Must match from the root
        return fnmatch.fnmatch(rel_path_str, glob_pattern)

    # Non-rooted patterns with / can match anywhere in the path
    # Try matching from each directory level
    parts = rel_path_str.split("/")
    for i in range(len(parts)):
        sub_path = "/".join(parts[i:])
        if fnmatch.fnmatch(sub_path, glob_pattern):
            return True
    return False


def _matches_gitignore(
    rel_path_str: str,
    is_dir: bool,
    gitignore_patterns: list[str],
) -> bool:
    """Check if a path matches gitignore patterns.

    Processes patterns in order; negation patterns (``!``) can un-ignore
    previously matched paths.  Also checks parent directories: if a
    parent directory is ignored, the file inside it is ignored too.
    """
    # Build list of paths to check: all parent dirs, then the file/dir itself
    parts = rel_path_str.split("/")
    paths_to_check = [("/".join(parts[:i]), True) for i in range(1, len(parts))]
    paths_to_check.append((rel_path_str, is_dir))

    ignored = False
    for pattern in gitignore_patterns:
        if pattern.startswith("!"):
            neg_pattern = pattern[1:]
            for check_path, check_is_dir in paths_to_check:
                if _gitignore_pattern_matches(neg_pattern, check_path, check_is_dir):
                    ignored = False
                    break
        else:
            for check_path, check_is_dir in paths_to_check:
                if _gitignore_pattern_matches(pattern, check_path, check_is_dir):
                    ignored = True
                    break
    return ignored


def load_gitignore_patterns(docs_folder: Path) -> list[str]:
    """Load .gitignore patterns from the docs folder and its parents.

    Walks up from ``docs_folder`` to the filesystem root, collecting
    ``.gitignore`` files.  Patterns from parent directories are applied
    first (lower priority), then patterns from directories closer to
    ``docs_folder`` (higher priority), matching Git's behaviour.
    """
    gitignore_files: list[Path] = []
    current = docs_folder.resolve()
    while True:
        candidate = current / ".gitignore"
        if candidate.is_file():
            gitignore_files.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Reverse so parent patterns come first (lower priority)
    gitignore_files.reverse()

    all_patterns: list[str] = []
    for gi in gitignore_files:
        all_patterns.extend(_parse_gitignore(gi))
    return all_patterns


def should_ignore_path(
    path: Path,
    base_folder: Path,
    *,
    gitignore_patterns: list[str] | None = None,
) -> bool:
    """Check if a path should be ignored during indexing.

    Ignores:
    - Any path component starting with '.' (hidden files/dirs)
    - Common development directories (__pycache__, node_modules, venv, etc.)
    - .egg-info directories
    - OS metadata files (Thumbs.db)
    - Paths matching .gitignore patterns (when provided)

    Args:
        path: The file path to check.
        base_folder: The base folder for computing relative paths.
        gitignore_patterns: Pre-parsed gitignore patterns from
            :func:`load_gitignore_patterns`.

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
    if path.name in DEFAULT_IGNORE_FILES:
        return True

    # Check gitignore patterns
    if gitignore_patterns:
        rel_path_str = "/".join(rel_parts)
        is_dir = path.is_dir()
        if _matches_gitignore(rel_path_str, is_dir, gitignore_patterns):
            return True

    return False


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
