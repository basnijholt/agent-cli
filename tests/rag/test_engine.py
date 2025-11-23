"""Tests for RAG engine."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.rag import engine
from agent_cli.rag.models import ChatRequest, Message


def test_retrieve_context_direct() -> None:
    """Test direct usage of retrieve_context without async/HTTP."""
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

        retrieval = engine.retrieve_context(req, mock_collection, mock_reranker)

        assert retrieval is not None
        assert "Found it." in retrieval.context

        # Case 2: No context
        mock_search.return_value = MagicMock(context="", sources=[])

        retrieval = engine.retrieve_context(req, mock_collection, mock_reranker)

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
    mock_run_result.usage = None

    # We mock Agent.run on the class itself because each call creates a NEW instance
    with (
        patch("agent_cli.rag.engine.Agent.run", new_callable=AsyncMock) as mock_run,
        patch("agent_cli.rag.engine.search_context") as mock_search,
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
        # Should check if search was called
        mock_search.assert_called_once()
        # Verify Agent.run was called
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_process_chat_request_with_rag(tmp_path: Path) -> None:
    """Test chat request with RAG context."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    mock_run_result = MagicMock()
    mock_run_result.output = "RAG Response"
    mock_run_result.run_id = "test-id"
    mock_run_result.usage = None

    with (
        patch("agent_cli.rag.engine.Agent.run", new_callable=AsyncMock) as mock_run,
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
