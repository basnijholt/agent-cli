"""Tests for RAG utilities."""

from pathlib import Path
from typing import Any

from agent_cli.rag import utils


def test_chunk_text_simple() -> None:
    """Test simple text chunking."""
    text = "Hello world. This is a test."
    chunks = utils.chunk_text(text, chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_split() -> None:
    """Test chunking with splitting."""
    # Create a text with multiple sentences
    sentences = ["Sentence 1.", "Sentence 2.", "Sentence 3.", "Sentence 4."]
    text = " ".join(sentences)

    # Small chunk size to force split
    # "Sentence 1." is 11 chars.
    chunks = utils.chunk_text(text, chunk_size=25, overlap=0)

    # Expecting roughly: ["Sentence 1. Sentence 2.", "Sentence 3. Sentence 4."]
    # But strict length might vary.
    assert len(chunks) >= 2
    assert "Sentence 1." in chunks[0]
    assert "Sentence 4." in chunks[-1]


def test_chunk_text_overlap() -> None:
    """Test chunking with overlap."""
    text = "A. B. C. D. E. F."
    # Chunk size small enough to fit maybe 2-3 sentences
    # Overlap enough to repeat 1
    chunks = utils.chunk_text(text, chunk_size=6, overlap=3)

    # "A. B. " -> 6 chars
    # "C. D. " -> 6 chars
    # If overlap is used, we might see overlap.

    assert len(chunks) > 1  # Check for overlap if logic supports it strictly
    # For now just ensure no data loss
    reconstructed = "".join(chunks).replace(" ", "").replace(".", "")
    original = text.replace(" ", "").replace(".", "")
    # Reconstructed might be longer due to overlap
    assert len(reconstructed) >= len(original)


def test_load_document_text_txt(tmp_path: Path) -> None:
    """Test loading text file."""
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")

    content = utils.load_document_text(f)
    assert content == "hello world"


def test_load_document_text_unsupported(tmp_path: Path) -> None:
    """Test loading unsupported file."""
    f = tmp_path / "test.xyz"
    f.write_text("content", encoding="utf-8")

    content = utils.load_document_text(f)
    assert content is None


def test_load_document_text_markitdown(tmp_path: Path, mocker: Any) -> None:
    """Test loading document using MarkItDown (mocked)."""
    # Mock MarkItDown class
    mock_cls = mocker.patch("markitdown.MarkItDown")
    mock_instance = mock_cls.return_value
    mock_result = mock_instance.convert.return_value
    mock_result.text_content = "mocked content"

    # Create a dummy PDF file
    f = tmp_path / "test.pdf"
    f.touch()

    content = utils.load_document_text(f)

    assert content == "mocked content"
    mock_cls.assert_called_once()
    mock_instance.convert.assert_called_once_with(str(f))


def test_get_file_hash(tmp_path: Path) -> None:
    """Test file hashing."""
    f = tmp_path / "test.txt"
    f.write_text("content", encoding="utf-8")

    h1 = utils.get_file_hash(f)

    f.write_text("content", encoding="utf-8")  # Same content
    h2 = utils.get_file_hash(f)

    assert h1 == h2

    f.write_text("modified", encoding="utf-8")
    h3 = utils.get_file_hash(f)

    assert h1 != h3
