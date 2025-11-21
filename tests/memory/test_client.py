"""Tests for the standalone MemoryClient."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent_cli.memory.client import MemoryClient
from agent_cli.memory.models import ChatRequest, MemoryRetrieval

if TYPE_CHECKING:
    from pathlib import Path


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[str] = []

    def query(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Mock query."""
        del args, kwargs  # Unused
        return {
            "documents": [[]],
            "metadatas": [[]],
            "ids": [[]],
            "distances": [[]],
        }


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


@pytest.fixture
def client(tmp_path: Path) -> MemoryClient:
    """Create a memory client with stubs."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("agent_cli.memory.client.watch_memory_store"),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.get_reranker_model", return_value=_DummyReranker()),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.init_memory_collection", return_value=_FakeCollection()),
        )
        stack.enter_context(patch("agent_cli.memory.client.initial_index"))

        return MemoryClient(
            memory_path=tmp_path,
            openai_base_url="http://mock",
            start_watcher=False,
        )


@pytest.mark.asyncio
async def test_client_add_calls_engine(client: MemoryClient) -> None:
    """Test that add() delegates to the engine correctly."""
    with patch("agent_cli.memory.client.extract_and_store_facts_and_summaries") as mock_extract:
        await client.add("My name is Alice", conversation_id="test-conv")

        mock_extract.assert_called_once()
        call_kwargs = mock_extract.call_args.kwargs
        assert call_kwargs["user_message"] == "My name is Alice"
        assert call_kwargs["assistant_message"] is None
        assert call_kwargs["conversation_id"] == "test-conv"


@pytest.mark.asyncio
async def test_client_search_calls_engine(client: MemoryClient) -> None:
    """Test that search() delegates to augment_chat_request."""
    with patch("agent_cli.memory.client.augment_chat_request") as mock_augment:
        # Mock return: (request, retrieval, conversation_id, summaries)
        mock_retrieval = MemoryRetrieval(entries=[])
        mock_augment.return_value = (None, mock_retrieval, "test-conv", [])

        result = await client.search("Where is my car?", conversation_id="test-conv")

        mock_augment.assert_called_once()
        assert result == mock_retrieval

        # Check that it constructed a dummy request
        call_args = mock_augment.call_args[0]
        req = call_args[0]
        assert isinstance(req, ChatRequest)
        assert req.messages[0].content == "Where is my car?"
        assert req.memory_id == "test-conv"


@pytest.mark.asyncio
async def test_client_chat_calls_engine(client: MemoryClient) -> None:
    """Test that chat() delegates to process_chat_request."""
    with patch("agent_cli.memory.client.process_chat_request") as mock_process:
        mock_process.return_value = {"choices": []}

        messages = [{"role": "user", "content": "Hello"}]
        await client.chat(messages, conversation_id="test-conv", model="gpt-4o")

        mock_process.assert_called_once()
        args, kwargs = mock_process.call_args
        req = args[0] if args else kwargs["request"]

        assert [m.model_dump() for m in req.messages] == messages
        assert req.model == "gpt-4o"
        assert req.memory_id == "test-conv"
