"""Tests for the standalone MemoryClient."""

from __future__ import annotations

import asyncio
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
            "embeddings": [[]],
        }

    def get(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Mock get."""
        del args, kwargs
        return {
            "ids": [],
            "embeddings": None,
            "metadatas": [],
            "documents": [],
            "uris": None,
            "data": None,
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
        await client.chat(
            messages,
            conversation_id="test-conv",
            model="gpt-4o",
            api_key="sk-test-key",
        )

        mock_process.assert_called_once()
        args, kwargs = mock_process.call_args
        req = args[0] if args else kwargs["request"]
        # The api_key should be passed in kwargs or args, depending on signature of process_chat_request
        # process_chat_request(..., api_key=..., ...)

        # Check api_key in call kwargs
        assert kwargs.get("api_key") == "sk-test-key"

        assert [m.model_dump() for m in req.messages] == messages
        assert req.model == "gpt-4o"
        assert req.memory_id == "test-conv"


@pytest.mark.asyncio
async def test_client_startup_manual(tmp_path: Path) -> None:
    """Test that watcher is not started by default, but can be started manually."""
    # Create a simple async mock for the watcher

    async def _fake_watch(*_args: Any, **_kwargs: Any) -> None:
        try:
            # Use Event wait instead of sleep loop for better efficiency

            stop_event = asyncio.Event()

            await stop_event.wait()

        except asyncio.CancelledError:
            pass

    with ExitStack() as stack:
        mock_watch = stack.enter_context(patch("agent_cli.memory.client.watch_memory_store"))
        mock_watch.side_effect = _fake_watch

        stack.enter_context(
            patch("agent_cli.memory.client.get_reranker_model", return_value=_DummyReranker()),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.init_memory_collection", return_value=_FakeCollection()),
        )
        stack.enter_context(patch("agent_cli.memory.client.initial_index"))

        client = MemoryClient(
            memory_path=tmp_path,
            openai_base_url="http://mock",
            # start_watcher defaults to False now
        )

        mock_watch.assert_not_called()
        assert client._watch_task is None

        client.start()

        # Verify a task was created
        assert client._watch_task is not None
        assert not client._watch_task.done()

        # Stop
        await client.stop()
        assert client._watch_task is None


@pytest.mark.asyncio
async def test_client_context_manager(tmp_path: Path) -> None:
    """Test that context manager starts/stops watcher."""

    async def _fake_watch(*_args: Any, **_kwargs: Any) -> None:
        try:
            stop_event = asyncio.Event()

            await stop_event.wait()

        except asyncio.CancelledError:
            pass

    with ExitStack() as stack:
        mock_watch = stack.enter_context(patch("agent_cli.memory.client.watch_memory_store"))
        mock_watch.side_effect = _fake_watch

        stack.enter_context(
            patch("agent_cli.memory.client.get_reranker_model", return_value=_DummyReranker()),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.init_memory_collection", return_value=_FakeCollection()),
        )
        stack.enter_context(patch("agent_cli.memory.client.initial_index"))

        client_obj = MemoryClient(
            memory_path=tmp_path,
            openai_base_url="http://mock",
            start_watcher=False,
        )

        assert client_obj._watch_task is None

        async with client_obj as c:
            assert c is client_obj
            assert c._watch_task is not None
            mock_watch.assert_called_once()

        assert client_obj._watch_task is None
