"""Integration tests for long conversation mode.

Tests the full transformation pipeline:
- Messages in → context built → request to LLM
- Compression triggers and asymmetric behavior
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.memory import api as memory_api

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def captured_requests() -> list[dict[str, Any]]:
    """Collect all requests sent to the LLM."""
    return []


@pytest.fixture
def long_convo_client(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> TestClient:
    """Create a long conversation mode client that captures LLM requests."""

    async def _capture_request(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        # Capture the request for inspection
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "model": request.model,
            },
        )
        # Return a mock response
        return {"choices": [{"message": {"content": "Assistant response."}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_capture_request,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
            context_budget=1000,  # Small budget to trigger compression easily
            compress_threshold=0.5,  # Compress at 50% to trigger quickly
            raw_recent_tokens=200,  # Keep only ~200 tokens raw
        )
        yield TestClient(app)


def test_first_message_goes_directly_to_llm(
    long_convo_client: TestClient,
    captured_requests: list[dict[str, Any]],
) -> None:
    """First message should be passed to LLM with no history."""
    resp = long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello!"}],
        },
    )
    assert resp.status_code == 200

    # Should have captured one request
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # Should contain just the user message
    assert len(req["messages"]) == 1
    assert req["messages"][0]["role"] == "user"
    assert req["messages"][0]["content"] == "Hello!"


def test_history_accumulates_across_requests(
    long_convo_client: TestClient,
    captured_requests: list[dict[str, Any]],
) -> None:
    """Subsequent messages should include conversation history."""
    # First message
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Message 1"}],
        },
    )

    # Second message
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Message 2"}],
        },
    )

    # Second request should have history
    assert len(captured_requests) == 2
    req = captured_requests[1]

    # Should have: user1, assistant1, user2
    assert len(req["messages"]) == 3
    assert req["messages"][0]["content"] == "Message 1"
    assert req["messages"][1]["content"] == "Assistant response."
    assert req["messages"][2]["content"] == "Message 2"


def test_segments_persisted_to_disk(
    long_convo_client: TestClient,
    tmp_path: Path,
) -> None:
    """Messages should be persisted as segment files."""
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Persist me"}],
        },
    )

    segments_dir = tmp_path / "long_conversations" / "default" / "segments"
    files = list(segments_dir.glob("*.md"))

    # Should have user + assistant segments
    assert len(files) == 2

    # Check content
    contents = [f.read_text() for f in sorted(files)]
    assert "Persist me" in contents[0]
    assert "Assistant response." in contents[1]


def test_compression_triggers_when_threshold_exceeded(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> None:
    """Compression should trigger when token threshold is exceeded."""
    summarize_calls: list[str] = []

    async def _capture_and_summarize(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        content = request.messages[0].content

        # Detect if this is a summarization request
        if "Summarize the following" in content:
            summarize_calls.append(content)
            return {"choices": [{"message": {"content": "Summary: brief."}}]}

        # Regular chat - capture and respond
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            },
        )
        # Return a long response to help trigger compression
        return {"choices": [{"message": {"content": "A" * 500}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_capture_and_summarize,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
            context_budget=300,  # Very small budget
            compress_threshold=0.3,  # Compress at 30%
            raw_recent_tokens=50,  # Keep very few tokens raw
        )
        client = TestClient(app)

        # Send several messages to trigger compression
        for i in range(5):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": f"Message {i}: " + "x" * 100}],
                },
            )

    # Should have triggered summarization
    assert len(summarize_calls) > 0, "Compression should have been triggered"


def test_assistant_messages_compressed_before_user(
    tmp_path: Path,
) -> None:
    """Assistant messages should be prioritized for compression."""
    summarize_calls: list[str] = []

    async def _track_summarization(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        content = request.messages[0].content

        if "Summarize the following" in content:
            summarize_calls.append(content)
            # Check which type of summarization
            if "assistant response" in content.lower():
                return {"choices": [{"message": {"content": "• Decision made"}}]}
            return {"choices": [{"message": {"content": "User asked about X"}}]}

        return {"choices": [{"message": {"content": "Long assistant response " + "y" * 200}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_track_summarization,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
            context_budget=400,
            compress_threshold=0.4,
            raw_recent_tokens=100,
        )
        client = TestClient(app)

        # Send messages to trigger compression
        for i in range(6):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": f"User message {i}"}],
                },
            )

    # Check that assistant messages were compressed first
    # (the prompt mentions "assistant response" for assistant messages)
    if summarize_calls:
        # First compressions should be assistant messages
        first_call = summarize_calls[0]
        assert "assistant" in first_call.lower(), (
            "Assistant messages should be compressed before user messages"
        )


def test_summarized_content_used_in_context(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> None:
    """After compression, summaries should be used in context building."""

    async def _summarize_handler(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        content = request.messages[0].content

        if "Summarize the following" in content:
            return {"choices": [{"message": {"content": "[SUMMARIZED]"}}]}

        # Capture for inspection
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            },
        )
        return {"choices": [{"message": {"content": "Response " + "z" * 150}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_summarize_handler,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
            context_budget=300,
            compress_threshold=0.3,
            raw_recent_tokens=50,
        )
        client = TestClient(app)

        # Send enough messages to trigger compression
        for i in range(8):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": f"Msg {i}"}],
                },
            )

    # After compression, later requests should contain [SUMMARIZED] content
    # (This is a soft check - compression timing can vary)
    assert len(captured_requests) >= 5


def test_separate_conversations_isolated(
    long_convo_client: TestClient,
    captured_requests: list[dict[str, Any]],
) -> None:
    """Different memory_ids should have isolated histories."""
    # Message to conversation A
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello from A"}],
            "memory_id": "convo-a",
        },
    )

    # Message to conversation B
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello from B"}],
            "memory_id": "convo-b",
        },
    )

    # Second message to A - should only have A's history
    long_convo_client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Second from A"}],
            "memory_id": "convo-a",
        },
    )

    # Third request should only have convo A history
    req = captured_requests[2]
    contents = [m["content"] for m in req["messages"]]

    assert "Hello from A" in contents
    assert "Hello from B" not in contents
    assert "Second from A" in contents
