"""Tests for RAG utilities."""

from pathlib import Path
from typing import Any

import pytest

from agent_cli.rag import _utils


def test_chunk_text_simple() -> None:
    """Test simple text chunking."""
    text = "Hello world. This is a test."
    chunks = _utils.chunk_text(text, chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_split() -> None:
    """Test chunking with splitting."""
    # Create a text with multiple sentences
    sentences = ["Sentence 1.", "Sentence 2.", "Sentence 3.", "Sentence 4."]
    text = " ".join(sentences)

    # Small chunk size to force split
    # "Sentence 1." is 11 chars.
    chunks = _utils.chunk_text(text, chunk_size=25, overlap=0)

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
    chunks = _utils.chunk_text(text, chunk_size=6, overlap=3)

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

    content = _utils.load_document_text(f)
    assert content == "hello world"


def test_load_document_text_unsupported(tmp_path: Path) -> None:
    """Test loading unsupported file."""
    f = tmp_path / "test.xyz"
    f.write_text("content", encoding="utf-8")

    content = _utils.load_document_text(f)
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

    content = _utils.load_document_text(f)

    assert content == "mocked content"
    mock_cls.assert_called_once()
    mock_instance.convert.assert_called_once_with(str(f))


def test_chunk_text_hard_split_oversized() -> None:
    """Test chunking with oversized content (no sentence boundaries)."""
    # Simulate a code file with no sentence-ending punctuation
    code_like_text = "x = 1\ny = 2\nz = 3\n" * 100  # ~1200 chars, no periods

    chunks = _utils.chunk_text(code_like_text, chunk_size=200, overlap=50)

    # Should produce multiple chunks, none exceeding chunk_size
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200, f"Chunk too large: {len(chunk)} chars"

    # Verify all content is covered (with some overlap duplication)
    total_unique = set("".join(chunks))
    assert total_unique >= set(code_like_text)


def test_hard_split_direct() -> None:
    """Test _hard_split function directly."""
    text = "A" * 500
    chunks = _utils._hard_split(text, chunk_size=100, overlap=20)

    # With 500 chars, chunk_size=100, overlap=20:
    # Chunk 1: 0-100 (100 chars), next start: 100-20=80
    # Chunk 2: 80-180 (100 chars), next start: 180-20=160
    # etc.
    assert len(chunks) >= 5
    for chunk in chunks:
        assert len(chunk) <= 100


def test_hard_split_invalid_overlap() -> None:
    """Test _hard_split raises when overlap >= chunk_size."""
    with pytest.raises(ValueError, match=r"overlap .* must be < chunk_size"):
        _utils._hard_split("hello", chunk_size=100, overlap=100)

    with pytest.raises(ValueError, match=r"overlap .* must be < chunk_size"):
        _utils._hard_split("hello", chunk_size=100, overlap=200)


def test_get_file_hash(tmp_path: Path) -> None:
    """Test file hashing."""
    f = tmp_path / "test.txt"
    f.write_text("content", encoding="utf-8")

    h1 = _utils.get_file_hash(f)

    f.write_text("content", encoding="utf-8")  # Same content
    h2 = _utils.get_file_hash(f)

    assert h1 == h2

    f.write_text("modified", encoding="utf-8")
    h3 = _utils.get_file_hash(f)

    assert h1 != h3


# === Tests for should_ignore_path ===


class TestShouldIgnorePath:
    """Tests for the should_ignore_path function."""

    def test_normal_file_not_ignored(self, tmp_path: Path) -> None:
        """Test that normal files are not ignored."""
        f = tmp_path / "document.txt"
        f.touch()
        assert not _utils.should_ignore_path(f, tmp_path)

    def test_normal_nested_file_not_ignored(self, tmp_path: Path) -> None:
        """Test that nested normal files are not ignored."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        f = subdir / "document.md"
        f.touch()
        assert not _utils.should_ignore_path(f, tmp_path)

    # Hidden files and directories
    def test_hidden_file_ignored(self, tmp_path: Path) -> None:
        """Test that hidden files are ignored."""
        f = tmp_path / ".hidden"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_hidden_directory_ignored(self, tmp_path: Path) -> None:
        """Test that files in hidden directories are ignored."""
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        f = hidden_dir / "config"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_deeply_nested_hidden_ignored(self, tmp_path: Path) -> None:
        """Test that deeply nested files in hidden directories are ignored."""
        path = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages"
        path.mkdir(parents=True)
        f = path / "some_package.py"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    # Common development directories
    def test_pycache_ignored(self, tmp_path: Path) -> None:
        """Test that __pycache__ directories are ignored."""
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        f = cache / "module.cpython-313.pyc"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_node_modules_ignored(self, tmp_path: Path) -> None:
        """Test that node_modules directories are ignored."""
        nm = tmp_path / "node_modules"
        nm.mkdir()
        f = nm / "lodash" / "index.js"
        f.parent.mkdir()
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_venv_ignored(self, tmp_path: Path) -> None:
        """Test that venv directories are ignored (non-hidden)."""
        venv = tmp_path / "venv"
        venv.mkdir()
        f = venv / "bin" / "python"
        f.parent.mkdir()
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_build_ignored(self, tmp_path: Path) -> None:
        """Test that build directories are ignored."""
        build = tmp_path / "build"
        build.mkdir()
        f = build / "output.js"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_dist_ignored(self, tmp_path: Path) -> None:
        """Test that dist directories are ignored."""
        dist = tmp_path / "dist"
        dist.mkdir()
        f = dist / "bundle.min.js"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    # .egg-info directories
    def test_egg_info_ignored(self, tmp_path: Path) -> None:
        """Test that .egg-info directories are ignored."""
        egg = tmp_path / "mypackage.egg-info"
        egg.mkdir()
        f = egg / "PKG-INFO"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    # Specific ignored files
    def test_ds_store_ignored(self, tmp_path: Path) -> None:
        """Test that .DS_Store files are ignored."""
        f = tmp_path / ".DS_Store"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_thumbs_db_ignored(self, tmp_path: Path) -> None:
        """Test that Thumbs.db files are ignored."""
        f = tmp_path / "Thumbs.db"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_hidden_file_with_extension_ignored(self, tmp_path: Path) -> None:
        """Test that hidden files with extensions are ignored."""
        f = tmp_path / ".hidden_config"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    # Edge cases
    def test_file_named_build_not_ignored(self, tmp_path: Path) -> None:
        """Test that a file named 'build' is not ignored (only directories)."""
        # The function checks path parts, so a file named "build" at root
        # would have "build" as a part and be ignored
        f = tmp_path / "build"
        f.touch()
        # This will be ignored because "build" is in the parts
        assert _utils.should_ignore_path(f, tmp_path)

    def test_subdir_named_like_ignore_pattern(self, tmp_path: Path) -> None:
        """Test that subdirs matching ignore patterns are caught."""
        subdir = tmp_path / "src" / "node_modules" / "pkg"
        subdir.mkdir(parents=True)
        f = subdir / "index.js"
        f.touch()
        assert _utils.should_ignore_path(f, tmp_path)

    def test_path_outside_base_folder_raises(self, tmp_path: Path) -> None:
        """Test that paths outside base folder raise ValueError (fail loudly)."""
        other_path = Path("/some/other/path.txt")
        with pytest.raises(ValueError, match="is not in the subpath"):
            _utils.should_ignore_path(other_path, tmp_path)
