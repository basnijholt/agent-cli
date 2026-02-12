"""Tests for RAG engine."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.rag import engine
from agent_cli.rag.engine import _convert_messages, _is_path_safe, truncate_context
from agent_cli.rag.models import ChatRequest, Message


def test_truncate_context_short() -> None:
    """Test truncation with context under the limit."""
    context = "Short context"
    assert truncate_context(context, max_chars=1000) == context


def test_truncate_context_long() -> None:
    """Test truncation with context over the limit."""
    chunks = ["Chunk 1", "Chunk 2", "Chunk 3", "Chunk 4"]
    context = "\n\n---\n\n".join(chunks)

    result = truncate_context(context, max_chars=30)

    # Should keep only complete chunks that fit
    assert "Chunk 1" in result
    assert "Chunk 4" not in result
    # Should not cut mid-chunk
    assert result.count("---") < 3


def test_truncate_context_preserves_separator() -> None:
    """Test that truncation preserves chunk separators."""
    context = "A\n\n---\n\nB\n\n---\n\nC"
    result = truncate_context(context, max_chars=20)

    # The separator should be intact between kept chunks
    if "\n\n---\n\n" in result:
        parts = result.split("\n\n---\n\n")
        assert all(p.strip() for p in parts)


def test_is_path_safe_within_base(tmp_path: Path) -> None:
    """Test path validation for safe paths."""
    base = tmp_path / "docs"
    base.mkdir()
    safe_file = base / "test.txt"
    safe_file.touch()

    assert _is_path_safe(base, safe_file) is True
    assert _is_path_safe(base, base / "subdir" / "file.txt") is True


def test_is_path_safe_outside_base(tmp_path: Path) -> None:
    """Test path validation rejects paths outside base."""
    base = tmp_path / "docs"
    base.mkdir()

    # Parent directory
    assert _is_path_safe(base, tmp_path / "other.txt") is False

    # Path traversal attempt
    assert _is_path_safe(base, base / ".." / "secret.txt") is False


def test_is_path_safe_symlink_escape(tmp_path: Path) -> None:
    """Test path validation handles symlink escape attempts."""
    base = tmp_path / "docs"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")

    # Create symlink inside base pointing outside
    symlink = base / "escape"
    try:
        symlink.symlink_to(outside)
        # The resolved path should be detected as outside
        assert _is_path_safe(base, symlink) is False
    except OSError:
        # Symlinks may not be supported on all systems
        pass


def test_convert_messages_skips_empty_system() -> None:
    """Test that empty system messages are filtered out."""
    messages = [
        Message(role="system", content=""),
        Message(role="user", content="Hello"),
        Message(role="user", content="Question"),
    ]

    history, user_prompt = _convert_messages(messages)

    # Empty system message should be skipped
    assert user_prompt == "Question"
    # Only the first user message should be in history (system was skipped)
    assert len(history) == 1


def test_convert_messages_keeps_nonempty_system() -> None:
    """Test that non-empty system messages are preserved."""
    messages = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Question"),
    ]

    history, user_prompt = _convert_messages(messages)

    assert user_prompt == "Question"
    assert len(history) == 1


def test_retrieve_context_direct() -> None:
    """Test direct usage of _retrieve_context without async/HTTP."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    with patch("agent_cli.rag.engine.search_context") as mock_search:
        # Case 1: Context found
        mock_search.return_value = MagicMock(
            context="Found it.",
            sources=[{"source": "doc1"}],
        )

        req = ChatRequest(
            model="test",
            messages=[Message(role="user", content="Query")],
        )

        retrieval = engine._retrieve_context(req, mock_collection, mock_reranker)

        assert retrieval is not None
        assert "Found it." in retrieval.context

        # Case 2: No context
        mock_search.return_value = MagicMock(context="", sources=[])

        retrieval = engine._retrieve_context(req, mock_collection, mock_reranker)

        assert retrieval is None


@pytest.mark.asyncio
async def test_process_chat_request_no_rag(tmp_path: Path) -> None:
    """Test chat request without RAG (no retrieval context)."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    # Mock Agent Run
    mock_run_result = MagicMock()
    mock_run_result.output = "Response"
    mock_run_result.run_id = "test-id"
    mock_run_result.usage.return_value = MagicMock(
        input_tokens=10,
        output_tokens=10,
        total_tokens=20,
    )

    # We mock Agent.run on the class itself because each call creates a NEW instance
    with (
        patch("pydantic_ai.Agent.run", new_callable=AsyncMock) as mock_run,
        patch("agent_cli.rag.engine.search_context") as mock_search,
        patch("pydantic_ai.Agent.__init__", return_value=None) as mock_agent_init,
    ):
        mock_run.return_value = mock_run_result
        # Mock retrieval to return empty
        mock_search.return_value = MagicMock(context="")

        req = ChatRequest(
            model="test",
            messages=[Message(role="user", content="Hello")],
        )

        resp = await engine.process_chat_request(
            req,
            mock_collection,
            mock_reranker,
            "http://mock",
            docs_folder=tmp_path,
        )

        assert resp["choices"][0]["message"]["content"] == "Response"
        mock_search.assert_called_once()
        mock_run.assert_called_once()

        # Verify system_prompt is an empty tuple, not an empty string
        # (empty strings cause errors on providers like Vertex AI)
        init_kwargs = mock_agent_init.call_args
        assert init_kwargs.kwargs["system_prompt"] == ()


@pytest.mark.asyncio
async def test_process_chat_request_with_rag(tmp_path: Path) -> None:
    """Test chat request with RAG context."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    mock_run_result = MagicMock()
    mock_run_result.output = "RAG Response"
    mock_run_result.run_id = "test-id"
    mock_run_result.usage.return_value = MagicMock(
        input_tokens=15,
        output_tokens=20,
        total_tokens=35,
    )

    with (
        patch("pydantic_ai.Agent.run", new_callable=AsyncMock) as mock_run,
        patch("agent_cli.rag.engine.search_context") as mock_search,
    ):
        mock_run.return_value = mock_run_result
        # Return some context
        mock_search.return_value = MagicMock(
            context="Relevant info.",
            sources=[{"source": "doc1"}],
        )

        req = ChatRequest(
            model="test",
            messages=[Message(role="user", content="Question")],
        )

        resp = await engine.process_chat_request(
            req,
            mock_collection,
            mock_reranker,
            "http://mock",
            docs_folder=tmp_path,
        )

        # Check if sources are added
        assert resp["rag_sources"] is not None
        assert resp["choices"][0]["message"]["content"] == "RAG Response"

        # We can't easily check internal tool state here without deeper spying,
        # but we verified the context retrieval part.
        mock_run.assert_called_once()
