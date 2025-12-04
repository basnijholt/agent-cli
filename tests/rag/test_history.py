"""Test history preservation in RAG engine."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse

from agent_cli.rag import engine
from agent_cli.rag.models import ChatRequest, Message


@pytest.mark.asyncio
async def test_process_chat_request_preserves_history(tmp_path: Path) -> None:
    """Test that conversation history is correctly passed to the agent."""
    mock_collection = MagicMock()
    mock_reranker = MagicMock()

    # Mock Agent Run
    mock_run_result = MagicMock()
    mock_run_result.output = "Response"
    mock_run_result.run_id = "test-id"
    mock_run_result.usage.return_value = None

    with (
        patch("pydantic_ai.Agent.run", new_callable=AsyncMock) as mock_run,
        patch("agent_cli.rag.engine.search_context") as mock_search,
    ):
        mock_run.return_value = mock_run_result
        mock_search.return_value = MagicMock(context="")  # No RAG context for this test

        # Create a multi-turn conversation
        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content="Question 1"),
            Message(role="assistant", content="Answer 1"),
            Message(role="user", content="Question 2"),
        ]
        req = ChatRequest(model="test", messages=messages)

        await engine.process_chat_request(
            req,
            mock_collection,
            mock_reranker,
            "http://mock",
            docs_folder=tmp_path,
        )

        # Verify Agent.run was called
        mock_run.assert_called_once()

        # Check arguments
        call_args = mock_run.call_args
        # positional args: prompt (user_prompt)
        prompt = call_args[0][0]
        assert prompt == "Question 2"

        # keyword args: message_history
        history = call_args[1]["message_history"]
        assert len(history) == 3

        # Verify types and content of history
        assert isinstance(history[0], ModelRequest)
        assert history[0].parts[0].content == "System prompt"

        assert isinstance(history[1], ModelRequest)
        assert history[1].parts[0].content == "Question 1"

        assert isinstance(history[2], ModelResponse)
        assert history[2].parts[0].content == "Answer 1"
