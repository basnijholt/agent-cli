"""Tests for RAG engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.rag import engine
from agent_cli.rag.models import ChatRequest, Message


@pytest.mark.asyncio
async def test_process_chat_request_no_rag() -> None:
    """Test chat request without RAG (no retrieval context)."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()
    mock_client = AsyncMock()

    # Mock forward request
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
    mock_client.post.return_value = mock_response

    # Mock retrieval to return empty
    with patch("agent_cli.rag.engine.search_context") as mock_search:
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
            mock_client,
        )

        assert resp["choices"][0]["message"]["content"] == "Response"
        # Should check if search was called
        mock_search.assert_called_once()


@pytest.mark.asyncio
async def test_process_chat_request_with_rag() -> None:
    """Test chat request with RAG context."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()
    mock_client = AsyncMock()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "RAG Response"}}]}
    mock_client.post.return_value = mock_response

    with patch("agent_cli.rag.engine.search_context") as mock_search:
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
            mock_client,
        )

        # Check if sources are added
        assert resp["rag_sources"] is not None

        # Check if client.post was called with augmented message
        call_args = mock_client.post.call_args
        assert call_args is not None
        json_body = call_args[1]["json"]
        last_msg = json_body["messages"][-1]["content"]

        assert "Context from documentation" in last_msg
        assert "Relevant info." in last_msg
        assert "Question: Question" in last_msg
