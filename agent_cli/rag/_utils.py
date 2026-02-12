"""Utility functions for RAG: Document loading and chunking."""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
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


@dataclass(frozen=True)
class GitignorePattern:
    """A normalized gitignore pattern plus the source directory context."""

    pattern: str
    negated: bool
    dir_only: bool
    anchored: bool
    has_slash: bool
    base_prefix: tuple[str, ...]


def _normalize_gitignore_line(line: str) -> tuple[bool, str] | None:
    """Normalize one .gitignore line.

    Returns:
        ``None`` if the line should be ignored, otherwise ``(negated, pattern)``.

    """
    line = line.strip()
    if not line:
        return None
    if line.startswith((r"\#", r"\!")):
        return False, line[1:]
    if line.startswith("#"):
        return None

    negated = line.startswith("!")
    if negated:
        line = line[1:]
        if not line:
            return None
    return negated, line


def _parse_gitignore(gitignore_path: Path, docs_folder: Path) -> list[GitignorePattern]:
    """Parse one .gitignore file into normalized rule objects."""
    try:
        text = gitignore_path.read_text(errors="ignore")
    except OSError:
        return []

    try:
        base_prefix = docs_folder.resolve().relative_to(gitignore_path.parent.resolve()).parts
    except ValueError:
        return []

    patterns: list[GitignorePattern] = []
    for raw_line in text.splitlines():
        normalized = _normalize_gitignore_line(raw_line)
        if normalized is None:
            continue
        negated, line = normalized

        dir_only = line.endswith("/")
        if dir_only:
            line = line.rstrip("/")

        anchored = line.startswith("/")
        if anchored:
            line = line.lstrip("/")

        if not line:
            continue

        patterns.append(
            GitignorePattern(
                pattern=line,
                negated=negated,
                dir_only=dir_only,
                anchored=anchored,
                has_slash="/" in line,
                base_prefix=base_prefix,
            ),
        )
    return patterns


@lru_cache(maxsize=512)
def _compile_gitignore_regex(pattern: str) -> re.Pattern[str]:
    """Compile a gitignore-like pattern into a regex.

    This keeps the key semantics needed here:
    - ``*`` does not cross path separators
    - ``**`` may cross path separators
    """
    regex_parts: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # Collapse runs like ** or ***
                while i + 1 < len(pattern) and pattern[i + 1] == "*":
                    i += 1
                if i + 1 < len(pattern) and pattern[i + 1] == "/":
                    regex_parts.append("(?:.*/)?")
                    i += 1
                else:
                    regex_parts.append(".*")
            else:
                regex_parts.append("[^/]*")
        elif char == "?":
            regex_parts.append("[^/]")
        else:
            regex_parts.append(re.escape(char))
        i += 1

    return re.compile(f"^{''.join(regex_parts)}$")


def _gitignore_rule_matches(
    rule: GitignorePattern,
    rel_parts: tuple[str, ...],
    is_dir: bool,
) -> bool:
    """Check whether one parsed gitignore rule matches one path."""
    if rule.dir_only and not is_dir:
        return False
    if not rel_parts:
        return False

    path_parts = (*rule.base_prefix, *rel_parts)
    if not path_parts:
        return False

    # No-slash patterns match only the basename at any depth.
    # Ancestor directories are handled by `_matches_gitignore`.
    if not rule.has_slash and not rule.anchored:
        return fnmatch.fnmatchcase(path_parts[-1], rule.pattern)

    rel_path_str = "/".join(path_parts)
    return bool(_compile_gitignore_regex(rule.pattern).fullmatch(rel_path_str))


def _is_path_ignored_by_rules(
    rel_parts: tuple[str, ...],
    is_dir: bool,
    gitignore_patterns: list[GitignorePattern],
) -> bool:
    """Evaluate gitignore rules for a single path."""
    ignored = False
    for rule in gitignore_patterns:
        if _gitignore_rule_matches(rule, rel_parts, is_dir):
            ignored = not rule.negated
    return ignored


def _matches_gitignore(
    rel_path_str: str,
    is_dir: bool,
    gitignore_patterns: list[GitignorePattern],
) -> bool:
    """Check if a path matches gitignore patterns.

    Processes patterns in order; negation patterns (``!``) can un-ignore
    previously matched paths. Parent directories are evaluated separately:
    if any parent directory is ignored, the file inside remains ignored.
    """
    parts = tuple(part for part in rel_path_str.split("/") if part)
    if not parts:
        return False

    # If any ancestor directory is ignored, this path is ignored too.
    for i in range(1, len(parts)):
        if _is_path_ignored_by_rules(parts[:i], is_dir=True, gitignore_patterns=gitignore_patterns):
            return True

    return _is_path_ignored_by_rules(parts, is_dir, gitignore_patterns)


def load_gitignore_patterns(docs_folder: Path) -> list[GitignorePattern]:
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

    all_patterns: list[GitignorePattern] = []
    for gi in gitignore_files:
        all_patterns.extend(_parse_gitignore(gi, docs_folder))
    return all_patterns


def should_ignore_path(
    path: Path,
    base_folder: Path,
    *,
    gitignore_patterns: list[GitignorePattern] | None = None,
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
