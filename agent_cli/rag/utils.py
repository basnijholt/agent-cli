"""Utility functions for RAG: Document loading and chunking."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

import docx
from pypdf import PdfReader

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
logger = logging.getLogger("agent_cli.rag.utils")


def load_document_text(file_path: Path) -> str | None:
    """Load text from a file path."""
    suffix = file_path.suffix.lower()

    try:
        if suffix in {
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
        }:
            return file_path.read_text(errors="ignore")

        if suffix == ".pdf":
            return _load_pdf(file_path)

        if suffix in {".docx", ".doc"}:
            return _load_docx(file_path)

        return None  # Unsupported
    except Exception:
        logger.exception("Failed to load %s", file_path)
        return None


def _load_pdf(file_path: Path) -> str | None:
    try:
        reader = PdfReader(file_path)
        return "\n\n".join(page.extract_text() for page in reader.pages if page.extract_text())
    except Exception:
        logger.exception("Error reading PDF %s", file_path)
        return None


def _load_docx(file_path: Path) -> str | None:
    try:
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception:
        logger.exception("Error reading DOCX %s", file_path)
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
                    overlap_buffer.insert(0, s)
                    overlap_size += len(s)
                else:
                    break

            current = overlap_buffer
            current_size = overlap_size

        current.append(sentence)
        current_size += sentence_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def get_file_hash(file_path: Path) -> str:
    """Get hash of file content."""
    return hashlib.md5(file_path.read_bytes(), usedforsecurity=False).hexdigest()
