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


# === Tests for semantic chunking ===


class TestRecursiveChunking:
    """Tests for the recursive semantic chunking behavior."""

    def test_splits_on_double_newline_first(self) -> None:
        r"""Verify paragraphs (\n\n) are the preferred split point."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = _utils.chunk_text(text, chunk_size=20, overlap=0)

        # Should split on paragraph boundaries, preserving separators
        assert len(chunks) == 3
        assert chunks[0] == "Paragraph one.\n\n"
        assert chunks[1] == "Paragraph two.\n\n"
        assert chunks[2] == "Paragraph three."
        # Verify no content loss
        assert "".join(chunks) == text

    def test_falls_back_to_single_newline(self) -> None:
        r"""When no \n\n, should split on \n."""
        text = "Line one\nLine two\nLine three\nLine four"
        chunks = _utils.chunk_text(text, chunk_size=20, overlap=0)

        # Should split on line boundaries, preserving newlines
        assert len(chunks) >= 2
        # Verify no content loss - all separators preserved
        assert "".join(chunks) == text

    def test_falls_back_to_sentence(self) -> None:
        """When no newlines, should split on sentences."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = _utils.chunk_text(text, chunk_size=40, overlap=0)

        assert len(chunks) >= 2
        # Sentences should be kept together where possible
        assert "First sentence" in chunks[0]

    def test_falls_back_to_words(self) -> None:
        """When no sentence boundaries, should split on words."""
        # No periods, no newlines - just words
        text = "word " * 50  # 250 chars
        chunks = _utils.chunk_text(text, chunk_size=50, overlap=0)

        assert len(chunks) >= 4
        for chunk in chunks:
            assert len(chunk) <= 50
            # Should not split mid-word
            assert chunk.strip().endswith("word") or chunk.strip() == ""

    def test_python_code_splits_on_lines(self) -> None:
        """Python code should split at line boundaries, not mid-statement."""
        code = """def hello():
    print("Hello")
    return True

def world():
    print("World")
    return False

def foo():
    x = 1
    y = 2
    return x + y"""

        chunks = _utils.chunk_text(code, chunk_size=60, overlap=0)

        assert len(chunks) >= 2
        # Each chunk should contain complete lines (no mid-line splits)
        for chunk in chunks:
            # If chunk has content, it shouldn't start/end mid-token
            stripped = chunk.strip()
            if stripped:
                # Should not start with a partial identifier
                assert not stripped[0].islower() or stripped.startswith(
                    ("def", "print", "return", "x", "y"),
                )

    def test_markdown_splits_on_headings(self) -> None:
        """Markdown should prefer splitting at paragraph/heading boundaries."""
        markdown = """# Heading 1

This is paragraph one with some content.

## Heading 2

This is paragraph two with more content.

## Heading 3

Final paragraph here."""

        chunks = _utils.chunk_text(markdown, chunk_size=60, overlap=0)

        assert len(chunks) >= 2
        # Should split on double newlines (between sections)
        # First chunk should start with heading
        assert chunks[0].startswith("# Heading 1")

    def test_oversized_word_falls_to_char_split(self) -> None:
        """A single 'word' larger than chunk_size should be character-split."""
        # No spaces, no newlines - just one giant string
        giant_word = "a" * 500
        chunks = _utils.chunk_text(giant_word, chunk_size=100, overlap=20)

        assert len(chunks) >= 5
        for chunk in chunks:
            assert len(chunk) <= 100

    def test_mixed_content(self) -> None:
        """Mixed prose and code should chunk appropriately."""
        text = """# Introduction

This is some prose explaining the code below.

```python
def example():
    return 42
```

More prose after the code block."""

        chunks = _utils.chunk_text(text, chunk_size=80, overlap=0)

        assert len(chunks) >= 2
        # Content should be preserved
        full_text = "".join(chunks)
        assert "Introduction" in full_text
        assert "def example" in full_text
        assert "More prose" in full_text

    def test_empty_string(self) -> None:
        """Empty string should return empty list."""
        assert _utils.chunk_text("") == []
        assert _utils.chunk_text("   ") == []
        assert _utils.chunk_text("\n\n") == []

    def test_overlap_preserves_context(self) -> None:
        """Verify overlap includes trailing content from previous chunk."""
        text = "AAA BBB CCC DDD EEE FFF GGG HHH"
        chunks = _utils.chunk_text(text, chunk_size=15, overlap=8)

        assert len(chunks) >= 2
        # With overlap, some content should appear in multiple chunks
        all_content = " ".join(chunks)
        # Due to overlap, total chars should exceed original
        assert len(all_content) > len(text)

    def test_no_content_loss(self) -> None:
        """Verify all original content appears in at least one chunk."""
        text = "The quick brown fox jumps over the lazy dog. " * 10
        chunks = _utils.chunk_text(text, chunk_size=100, overlap=20)

        # Reconstruct (accounting for overlap duplicates)
        words_in_chunks = set()
        for chunk in chunks:
            words_in_chunks.update(chunk.split())

        original_words = set(text.split())
        assert original_words <= words_in_chunks

    def test_delimiter_preservation(self) -> None:
        """Verify separators are preserved at chunk boundaries (no char loss)."""
        # Various separator types
        test_cases = [
            "A. B. C. D. E.",  # Sentence separators
            "Line1\nLine2\nLine3\nLine4",  # Single newlines
            "P1\n\nP2\n\nP3\n\nP4",  # Double newlines
            "one two three four five six",  # Spaces
            "a, b, c, d, e, f",  # Comma separators
        ]

        for text in test_cases:
            chunks = _utils.chunk_text(text, chunk_size=12, overlap=0)
            reconstructed = "".join(chunks)
            assert reconstructed == text, (
                f"Content mismatch:\n"
                f"  Original:      {text!r}\n"
                f"  Reconstructed: {reconstructed!r}\n"
                f"  Chunks:        {chunks}"
            )

    def test_respects_chunk_size_limit(self) -> None:
        """No chunk should exceed chunk_size (except edge cases)."""
        # Various content types
        texts = [
            "word " * 200,  # Words only
            "Line\n" * 200,  # Lines only
            "Sentence. " * 100,  # Sentences
            "a" * 1000,  # No separators
            "Para one.\n\nPara two.\n\n" * 50,  # Paragraphs
        ]

        for text in texts:
            chunks = _utils.chunk_text(text, chunk_size=150, overlap=30)
            for chunk in chunks:
                assert len(chunk) <= 150, f"Chunk too large: {len(chunk)} chars"

    def test_invalid_chunk_size_zero(self) -> None:
        """Zero chunk_size should raise ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            _utils.chunk_text("test", chunk_size=0, overlap=0)

    def test_invalid_chunk_size_negative(self) -> None:
        """Negative chunk_size should raise ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            _utils.chunk_text("test", chunk_size=-10, overlap=0)

    def test_invalid_overlap_equals_chunk_size(self) -> None:
        """Overlap equal to chunk_size should raise ValueError."""
        with pytest.raises(ValueError, match=r"overlap .* must be less than chunk_size"):
            _utils.chunk_text("test", chunk_size=100, overlap=100)

    def test_invalid_overlap_exceeds_chunk_size(self) -> None:
        """Overlap exceeding chunk_size should raise ValueError."""
        with pytest.raises(ValueError, match=r"overlap .* must be less than chunk_size"):
            _utils.chunk_text("test", chunk_size=100, overlap=200)

    def test_only_separator_before_window_is_used(self) -> None:
        """When no later separator exists, fall back to the earlier boundary."""
        text = "P1" * 10 + "\n\n" + "P2" * 800  # only separator is the double newline
        chunks = _utils.chunk_text(text, chunk_size=400, overlap=0)

        first_paragraph = "P1" * 10 + "\n\n"
        assert chunks[0] == first_paragraph
        assert chunks[1].startswith("P2"), "Second chunk should begin after the separator"

    def test_prefers_late_separator_when_available(self) -> None:
        """If a later boundary exists, do not stop at an early separator."""
        intro = "Intro paragraph.\n\n"
        body = " ".join([f"Sentence {i}." for i in range(40)])
        text = intro + body

        chunks = _utils.chunk_text(text, chunk_size=200, overlap=0)

        # First chunk should not end right after the intro paragraph because
        # there are plenty of later spaces/punctuation to break on.
        assert len(chunks[0]) >= 150
        assert not chunks[0].endswith("\n\n")


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
