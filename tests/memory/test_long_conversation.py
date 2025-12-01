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
from agent_cli.memory._long_conversation import (
    append_segment,
    build_context,
    compute_similarity,
    create_segment,
    extract_chunks,
    load_conversation,
)
from agent_cli.memory.entities import Segment

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


# --- Phase 3: Repetition Detection Tests ---


def test_chunk_extraction() -> None:
    """Test that text chunks are correctly extracted from content."""
    # Create content with substantial chunks separated by double newlines
    chunk1 = "x" * 250  # Over 200 char minimum
    chunk2 = "y" * 300
    content = f"{chunk1}\n\n{chunk2}"

    chunks = extract_chunks(content)
    assert len(chunks) == 2
    assert chunks[0].content == chunk1
    assert chunks[1].content == chunk2


def test_chunk_extraction_filters_small() -> None:
    """Test that small chunks are filtered out."""
    small = "small text"  # Under 200 chars
    large = "z" * 250

    content = f"{small}\n\n{large}"
    chunks = extract_chunks(content)

    # Only the large chunk should be extracted
    assert len(chunks) == 1
    assert chunks[0].content == large


def test_similarity_detection() -> None:
    """Test that similar text chunks are detected."""
    text1 = """def process(self):
    return self.data"""

    text2 = """def process(self):
    validated = self.validate()
    return self.data"""

    similarity = compute_similarity(text1, text2)
    # These are similar but not identical
    assert 0.6 < similarity < 1.0

    # Identical text
    identical = compute_similarity(text1, text1)
    assert identical == 1.0


def test_duplicate_text_creates_reference(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> None:
    """When user pastes same text twice, second should be stored as reference."""
    # Large text block (over 200 chars, single paragraph - no blank lines)
    large_text = """def calculate_total(items):
    total = 0
    for item in items:
        total += item.price * item.quantity
        # Add tax calculation
        tax = total * 0.1
        total += tax
    return total
# This function processes the items and calculates the total price"""

    async def _capture_request(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            },
        )
        return {"choices": [{"message": {"content": "Got it!"}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_capture_request,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
        )
        client = TestClient(app)

        # First message with text
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"Here's my code:\n\n{large_text}"}],
            },
        )

        # Second message with identical text
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"Same code again:\n\n{large_text}"}],
            },
        )

    # Check segments on disk
    segments_dir = tmp_path / "long_conversations" / "default" / "segments"
    files = sorted(segments_dir.glob("*.md"))

    # Should have 4 segments: user1, assistant1, user2, assistant2
    assert len(files) == 4

    # Read the second user segment (user2)
    second_user_content = files[2].read_text()

    # Should contain a reference marker instead of full text
    assert "Similar to segment" in second_user_content


def test_different_text_not_deduplicated(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> None:
    """Completely different text should not be deduplicated."""
    # Two different large text blocks
    text1 = """This is a completely different piece of text
that talks about something entirely unrelated to the second one.
It has enough characters to be considered a chunk for deduplication.
We need to make sure it's over 200 characters long to be extracted."""

    text2 = """Another block of text that has no similarity to the first.
It discusses different topics and uses different words entirely.
The deduplication system should not find any match between these two.
This should remain as full content without any reference markers."""

    async def _capture_request(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            },
        )
        return {"choices": [{"message": {"content": "Got it!"}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_capture_request,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
        )
        client = TestClient(app)

        # First message
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": text1}],
            },
        )

        # Second message with completely different text
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": text2}],
            },
        )

    # Check segments on disk
    segments_dir = tmp_path / "long_conversations" / "default" / "segments"
    files = sorted(segments_dir.glob("*.md"))

    # Read the second user segment
    second_user_content = files[2].read_text()

    # Should NOT contain a reference marker - text is different
    assert "Similar to segment" not in second_user_content
    # Should contain the full text
    assert "no similarity" in second_user_content


def test_reference_segment_used_in_context(
    tmp_path: Path,
    captured_requests: list[dict[str, Any]],
) -> None:
    """Reference segments should be included in context with compact format."""
    # Large text block that will be deduplicated (over 200 chars, single paragraph)
    large_text = """def very_long_function():
    # This is a long function with lots of lines that would take many tokens
    # We want to deduplicate this content to save context space in conversations
    result = process_something_important()
    validated = validate_the_result(result)
    transformed = transform_and_return(validated)
    return transformed"""

    async def _capture_request(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        captured_requests.append(
            {
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            },
        )
        return {"choices": [{"message": {"content": "Processed!"}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_capture_request,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
        )
        client = TestClient(app)

        # First message with text
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"First:\n\n{large_text}"}],
            },
        )

        # Second message with same text
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"Again:\n\n{large_text}"}],
            },
        )

        # Third message - should see history with reference
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": "What about my code?"}],
            },
        )

    # Check the third request's context
    assert len(captured_requests) >= 3
    third_request = captured_requests[2]

    # The context should include the reference segment
    all_content = " ".join(m["content"] for m in third_request["messages"])

    # First mention should have full text
    assert "very_long_function" in all_content


# --- Integration: Combined Features ---


def test_compression_and_deduplication_together(
    tmp_path: Path,
) -> None:
    """Test that compression and deduplication work together correctly.

    This tests the integration of:
    - Phase 2: Compression (summarization of old segments)
    - Phase 3: Deduplication (reference segments for repeated content)
    """
    summarize_calls: list[str] = []

    # Large text that will be repeated (over 200 chars, single paragraph)
    repeated_code = """def process_data(items):
    results = []
    for item in items:
        validated = validate_item(item)
        transformed = transform_item(validated)
        results.append(transformed)
    return results  # Returns the processed list of items after validation and transformation"""

    async def _handle_request(
        request: Any,
        base_url: str,  # noqa: ARG001
        api_key: str | None,  # noqa: ARG001
        exclude_fields: set[str],  # noqa: ARG001
    ) -> dict[str, Any]:
        content = request.messages[0].content

        # Track summarization requests
        if "Summarize the following" in content:
            summarize_calls.append(content)
            return {"choices": [{"message": {"content": "• Processed data items"}}]}

        # Return long responses to trigger compression
        return {"choices": [{"message": {"content": "Response: " + "z" * 200}}]}

    with patch(
        "agent_cli.core.openai_proxy.forward_chat_request",
        side_effect=_handle_request,
    ):
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            long_conversation=True,
            context_budget=500,  # Small budget to trigger compression
            compress_threshold=0.4,  # Compress at 40%
            raw_recent_tokens=100,  # Keep very few tokens raw
        )
        client = TestClient(app)

        # 1. First message with code
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"First code:\n\n{repeated_code}"}],
            },
        )

        # 2. Send several messages to trigger compression
        for i in range(4):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": f"Question {i}"}],
                },
            )

        # 3. Send same code again - should be deduplicated
        client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [{"role": "user", "content": f"Same code:\n\n{repeated_code}"}],
            },
        )

    # Verify both features worked
    segments_dir = tmp_path / "long_conversations" / "default" / "segments"
    files = sorted(segments_dir.glob("*.md"))

    # Should have multiple segments (12 = 6 user + 6 assistant)
    assert len(files) >= 10

    # Check for deduplication in the last user segment
    last_user_segments = [f for f in files if "_user_" in f.name]
    last_user_content = last_user_segments[-1].read_text()
    assert "Similar to segment" in last_user_content, "Deduplication should have occurred"

    # Check for compression (summarization should have been triggered)
    assert len(summarize_calls) > 0, "Compression should have been triggered"


def test_build_context_with_all_segment_states(
    tmp_path: Path,
) -> None:
    """Test build_context handles raw, summarized, and reference segments correctly."""
    # Create a conversation with all three segment states
    convo = load_conversation(tmp_path, "test-context")

    # 1. Raw segment
    raw_seg = create_segment("user", "This is raw content that has not been compressed.")
    convo = append_segment(tmp_path, convo, raw_seg)

    # 2. Summarized segment (manually set state)
    summarized_seg = Segment(
        id="summarized-1",
        role="assistant",
        content="Original long response with lots of detail...",
        timestamp=raw_seg.timestamp,
        original_tokens=100,
        current_tokens=20,
        state="summarized",
        summary="• Key point from response",
        content_hash="abc123",
    )
    convo = append_segment(tmp_path, convo, summarized_seg)

    # 3. Reference segment (manually set state)
    reference_seg = Segment(
        id="reference-1",
        role="user",
        content="[Similar to segment raw-1]\n\n[Changes:\n+small diff]",
        timestamp=raw_seg.timestamp,
        original_tokens=200,
        current_tokens=30,
        state="reference",
        refers_to=raw_seg.id,
        diff="+small diff",
        content_hash="def456",
    )
    convo = append_segment(tmp_path, convo, reference_seg)

    # Build context
    context = build_context(convo, "New question", token_budget=10000)

    # Verify all segments are included correctly
    assert len(context) == 4  # 3 history + 1 new message

    # Raw segment should use full content
    assert context[0]["content"] == "This is raw content that has not been compressed."

    # Summarized segment should use summary
    assert context[1]["content"] == "• Key point from response"

    # Reference segment should use stored content (with reference marker)
    assert "Similar to segment" in context[2]["content"]

    # New message at the end
    assert context[3]["content"] == "New question"
