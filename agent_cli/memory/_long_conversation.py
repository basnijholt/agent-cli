"""Long conversation mode: chronological context with asymmetric compression."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import yaml

from agent_cli.core.utils import atomic_write_text
from agent_cli.memory.entities import LongConversation, Segment

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger(__name__)

_LONG_CONVO_DIR = "long_conversations"
_SEGMENTS_DIR = "segments"
_METADATA_FILE = "metadata.json"
_FRONTMATTER_PARTS = 3  # Number of parts when splitting "---\nyaml\n---\ncontent"

# Asymmetric compression configuration
COMPRESSION_CONFIG = {
    "user": {
        "recent_turns": 20,  # Keep last N user turns raw
        "summary_target_ratio": 0.7,  # Compress to 70% (gentle)
        "preserve_quotes": True,  # Keep exact user phrasing
        "preserve_code": True,  # Never summarize code blocks
    },
    "assistant": {
        "recent_turns": 10,  # Keep last N assistant turns raw
        "summary_target_ratio": 0.2,  # Compress to 20% (aggressive)
        "keep_decisions": True,  # Preserve: "I decided to...", "I'll use..."
        "keep_conclusions": True,  # Preserve final answers
    },
}

# Summarization prompts for asymmetric compression
_USER_SUMMARIZE_PROMPT = """Summarize the following user message concisely while:
- Preserving ALL code blocks exactly as-is (do not modify or summarize code)
- Preserving direct quotes and specific requests
- Keeping technical details and requirements
- Maintaining the user's intent

Target length: approximately {target_ratio:.0%} of original.

User message:
{content}

Summary:"""

_ASSISTANT_SUMMARIZE_PROMPT = """Summarize the following assistant response aggressively to bullet points:
- Keep only key decisions ("I decided to...", "I'll use...")
- Keep only final conclusions and answers
- Remove explanations, elaborations, and filler
- Preserve any code that was provided

Target length: approximately {target_ratio:.0%} of original.

Assistant response:
{content}

Summary:"""


def estimate_tokens(text: str) -> int:
    """Estimate token count using ~4 chars per token heuristic."""
    return len(text) // 4


def content_hash(content: str) -> str:
    """Generate a hash for content deduplication."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _ensure_conversation_dir(memory_root: Path, conversation_id: str) -> Path:
    """Ensure conversation directory exists and return path."""
    conv_dir = memory_root / _LONG_CONVO_DIR / conversation_id
    conv_dir.mkdir(parents=True, exist_ok=True)
    (conv_dir / _SEGMENTS_DIR).mkdir(exist_ok=True)
    return conv_dir


def _segment_filename(segment: Segment, index: int) -> str:
    """Generate filename for a segment."""
    ts = segment.timestamp.strftime("%Y%m%d-%H%M%S")
    return f"{index:06d}_{segment.role}_{ts}.md"


def _render_segment_file(segment: Segment) -> str:
    """Render segment as markdown with YAML frontmatter."""
    metadata = {
        "id": segment.id,
        "role": segment.role,
        "timestamp": segment.timestamp.isoformat(),
        "original_tokens": segment.original_tokens,
        "current_tokens": segment.current_tokens,
        "state": segment.state,
        "content_hash": segment.content_hash,
    }
    if segment.summary:
        metadata["summary"] = segment.summary
    if segment.refers_to:
        metadata["refers_to"] = segment.refers_to
    if segment.diff:
        metadata["diff"] = segment.diff

    front_matter = yaml.safe_dump(metadata, default_flow_style=False, allow_unicode=True)
    return f"---\n{front_matter}---\n\n{segment.content}\n"


def _parse_segment_file(path: Path) -> Segment | None:
    """Parse a segment markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        LOGGER.warning("Failed to read segment file: %s", path)
        return None

    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < _FRONTMATTER_PARTS:
        return None

    try:
        metadata = yaml.safe_load(parts[1])
        content = parts[2].strip()
    except yaml.YAMLError:
        LOGGER.warning("Failed to parse segment frontmatter: %s", path)
        return None

    return Segment(
        id=metadata["id"],
        role=metadata["role"],
        content=content,
        timestamp=datetime.fromisoformat(metadata["timestamp"]),
        original_tokens=metadata["original_tokens"],
        current_tokens=metadata["current_tokens"],
        state=metadata.get("state", "raw"),
        summary=metadata.get("summary"),
        refers_to=metadata.get("refers_to"),
        diff=metadata.get("diff"),
        content_hash=metadata.get("content_hash", ""),
    )


def save_segment(
    memory_root: Path,
    conversation_id: str,
    segment: Segment,
    index: int,
) -> Path:
    """Save a segment to disk."""
    conv_dir = _ensure_conversation_dir(memory_root, conversation_id)
    segments_dir = conv_dir / _SEGMENTS_DIR
    filename = _segment_filename(segment, index)
    path = segments_dir / filename
    content = _render_segment_file(segment)
    atomic_write_text(path, content)
    LOGGER.debug("Saved segment %s to %s", segment.id, path)
    return path


def load_segments(memory_root: Path, conversation_id: str) -> list[Segment]:
    """Load all segments for a conversation, sorted by filename (chronological)."""
    conv_dir = memory_root / _LONG_CONVO_DIR / conversation_id / _SEGMENTS_DIR
    if not conv_dir.exists():
        return []

    segments = []
    for path in sorted(conv_dir.glob("*.md")):
        segment = _parse_segment_file(path)
        if segment:
            segments.append(segment)

    return segments


def save_conversation_metadata(
    memory_root: Path,
    conversation: LongConversation,
) -> None:
    """Save conversation metadata (excluding segment contents)."""
    conv_dir = _ensure_conversation_dir(memory_root, conversation.id)
    metadata = {
        "id": conversation.id,
        "target_context_tokens": conversation.target_context_tokens,
        "current_total_tokens": conversation.current_total_tokens,
        "compress_threshold": conversation.compress_threshold,
        "raw_recent_tokens": conversation.raw_recent_tokens,
        "segment_count": len(conversation.segments),
    }
    path = conv_dir / _METADATA_FILE
    atomic_write_text(path, json.dumps(metadata, indent=2))


def load_conversation(
    memory_root: Path,
    conversation_id: str,
    *,
    target_context_tokens: int = 150_000,
    compress_threshold: float = 0.8,
    raw_recent_tokens: int = 40_000,
) -> LongConversation:
    """Load a conversation from disk, or create new if not exists."""
    conv_dir = memory_root / _LONG_CONVO_DIR / conversation_id
    metadata_path = conv_dir / _METADATA_FILE

    # Load metadata if exists
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            target_context_tokens = metadata.get(
                "target_context_tokens",
                target_context_tokens,
            )
            compress_threshold = metadata.get("compress_threshold", compress_threshold)
            raw_recent_tokens = metadata.get("raw_recent_tokens", raw_recent_tokens)
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Failed to load conversation metadata, using defaults")

    # Load segments
    segments = load_segments(memory_root, conversation_id)

    # Calculate total tokens
    total_tokens = sum(s.current_tokens for s in segments)

    return LongConversation(
        id=conversation_id,
        segments=segments,
        target_context_tokens=target_context_tokens,
        current_total_tokens=total_tokens,
        compress_threshold=compress_threshold,
        raw_recent_tokens=raw_recent_tokens,
    )


def create_segment(
    role: str,
    content: str,
    *,
    state: str = "raw",
) -> Segment:
    """Create a new segment from content."""
    tokens = estimate_tokens(content)
    return Segment(
        id=str(uuid4()),
        role=role,  # type: ignore[arg-type]
        content=content,
        timestamp=datetime.now(UTC),
        original_tokens=tokens,
        current_tokens=tokens,
        state=state,  # type: ignore[arg-type]
        content_hash=content_hash(content),
    )


def append_segment(
    memory_root: Path,
    conversation: LongConversation,
    segment: Segment,
) -> LongConversation:
    """Append a segment to the conversation and persist."""
    # Add to conversation
    conversation.segments.append(segment)
    conversation.current_total_tokens += segment.current_tokens

    # Persist segment
    index = len(conversation.segments)
    save_segment(memory_root, conversation.id, segment, index)

    # Update metadata
    save_conversation_metadata(memory_root, conversation)

    return conversation


def get_recent_segments(
    conversation: LongConversation,
    max_tokens: int | None = None,
) -> list[Segment]:
    """Get recent segments up to max_tokens (newest last)."""
    if max_tokens is None:
        max_tokens = conversation.raw_recent_tokens

    result: list[Segment] = []
    token_count = 0

    # Iterate from newest to oldest
    for segment in reversed(conversation.segments):
        if token_count + segment.current_tokens > max_tokens:
            break
        result.append(segment)
        token_count += segment.current_tokens

    # Reverse to maintain chronological order
    return list(reversed(result))


def get_older_segments(
    conversation: LongConversation,
    recent_count: int,
) -> list[Segment]:
    """Get segments older than the recent window."""
    if recent_count >= len(conversation.segments):
        return []
    return conversation.segments[:-recent_count]


def build_context(
    conversation: LongConversation,
    new_message: str,
    token_budget: int,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Build context for LLM request, enforcing token budget.

    For Phase 1: No compression, just trim oldest messages if needed.
    """
    messages: list[dict[str, str]] = []

    # 1. System message (required)
    if system_prompt:
        system_msg = {"role": "system", "content": system_prompt}
        messages.append(system_msg)
        reserved_tokens = estimate_tokens(system_prompt)
    else:
        reserved_tokens = 0

    # 2. New user message (required, reserve space)
    new_user_msg = {"role": "user", "content": new_message}
    reserved_tokens += estimate_tokens(new_message)

    # 3. Calculate available budget for history
    available = token_budget - reserved_tokens

    # 4. Get recent segments that fit in budget
    recent_segments = get_recent_segments(conversation, max_tokens=available)

    # 5. Add history (Phase 1: no compression, just recent raw segments)
    for seg in recent_segments:
        # Use summary if available (for summarized segments), otherwise content
        content = seg.summary if seg.state == "summarized" and seg.summary else seg.content
        messages.append({"role": seg.role, "content": content})

    # 6. Add new user message
    messages.append(new_user_msg)

    return messages


def should_compress(conversation: LongConversation) -> bool:
    """Check if compression is needed."""
    usage_ratio = conversation.current_total_tokens / conversation.target_context_tokens
    return usage_ratio >= conversation.compress_threshold


def _count_recent_by_role(segments: list[Segment], role: str) -> int:
    """Count how many of the most recent segments match a role."""
    count = 0
    for seg in reversed(segments):
        if seg.role == role:
            count += 1
        # Only count contiguous recent segments
        if count >= COMPRESSION_CONFIG.get(role, {}).get("recent_turns", 10):
            break
    return count


def _is_recent_segment(
    segment: Segment,
    conversation: LongConversation,
    segment_index: int,
) -> bool:
    """Check if a segment is within the protected recent window."""
    # Check token-based recent window
    token_count = 0
    for i in range(len(conversation.segments) - 1, segment_index - 1, -1):
        token_count += conversation.segments[i].current_tokens
        if token_count > conversation.raw_recent_tokens:
            return segment_index > i

    # If we're within token budget, also check turn-based recent window
    role_config = COMPRESSION_CONFIG.get(segment.role, {})
    recent_turns = role_config.get("recent_turns", 10)

    # Count how many segments of this role are after this one
    turns_after = sum(
        1 for seg in conversation.segments[segment_index + 1 :] if seg.role == segment.role
    )
    return turns_after < recent_turns


def select_segments_to_compress(
    conversation: LongConversation,
    target_reduction: int | None = None,
) -> list[Segment]:
    """Select segments for compression, prioritizing assistant messages.

    Args:
        conversation: The conversation to analyze
        target_reduction: Target number of tokens to free up (optional)

    Returns:
        List of segments to compress, ordered by compression priority
        (assistant messages first, then by age - oldest first).

    """
    candidates: list[tuple[int, Segment]] = []

    for i, seg in enumerate(conversation.segments):
        # Skip already compressed segments
        if seg.state != "raw":
            continue
        # Skip system messages
        if seg.role == "system":
            continue
        # Skip recent segments
        if _is_recent_segment(seg, conversation, i):
            continue
        candidates.append((i, seg))

    # Sort: assistant messages first (they get compressed more aggressively),
    # then by timestamp (oldest first)
    candidates.sort(key=lambda x: (x[1].role == "user", x[1].timestamp))

    # If target_reduction specified, limit to segments needed
    if target_reduction is not None:
        selected = []
        potential_savings = 0
        for _i, seg in candidates:
            role_config = COMPRESSION_CONFIG.get(seg.role, {})
            target_ratio = role_config.get("summary_target_ratio", 0.5)
            savings = int(seg.current_tokens * (1 - target_ratio))
            selected.append(seg)
            potential_savings += savings
            if potential_savings >= target_reduction:
                break
        return selected

    return [seg for _i, seg in candidates]


# --- Compression ---


async def summarize_segment(
    segment: Segment,
    openai_base_url: str,
    model: str,
    api_key: str | None = None,
) -> str:
    """Summarize a segment using LLM with role-appropriate prompts.

    Uses asymmetric compression:
    - User messages: gentle summarization, preserve code and quotes
    - Assistant messages: aggressive summarization to bullet points
    """
    from agent_cli.core.openai_proxy import forward_chat_request  # noqa: PLC0415
    from agent_cli.memory.models import ChatRequest, Message  # noqa: PLC0415

    role_config = COMPRESSION_CONFIG.get(segment.role, COMPRESSION_CONFIG["assistant"])
    target_ratio = role_config.get("summary_target_ratio", 0.5)

    # Select the appropriate prompt template
    if segment.role == "user":
        prompt = _USER_SUMMARIZE_PROMPT.format(
            target_ratio=target_ratio,
            content=segment.content,
        )
    else:
        prompt = _ASSISTANT_SUMMARIZE_PROMPT.format(
            target_ratio=target_ratio,
            content=segment.content,
        )

    # Create summarization request
    request = ChatRequest(
        messages=[Message(role="user", content=prompt)],
        model=model,
        stream=False,
    )

    response = await forward_chat_request(
        request,
        openai_base_url,
        api_key,
        exclude_fields=set(),
    )

    if not isinstance(response, dict):
        LOGGER.warning("Unexpected response type during summarization: %s", type(response))
        return segment.content  # Return original on failure

    summary = _extract_assistant_content(response)
    if not summary:
        LOGGER.warning("Failed to extract summary from response")
        return segment.content  # Return original on failure

    return summary


async def compress_segment(
    memory_root: Path,
    conversation: LongConversation,
    segment: Segment,
    openai_base_url: str,
    model: str,
    api_key: str | None = None,
) -> Segment:
    """Compress a single segment and update it on disk.

    Returns the updated segment with summary and new token count.
    """
    LOGGER.info(
        "Compressing segment %s (role=%s, tokens=%d)",
        segment.id,
        segment.role,
        segment.current_tokens,
    )

    # Get summary from LLM
    summary = await summarize_segment(segment, openai_base_url, model, api_key)
    new_tokens = estimate_tokens(summary)

    # Update segment
    segment.summary = summary
    segment.current_tokens = new_tokens
    segment.state = "summarized"

    # Find segment index and save to disk
    for i, seg in enumerate(conversation.segments):
        if seg.id == segment.id:
            save_segment(memory_root, conversation.id, segment, i + 1)
            break

    LOGGER.info(
        "Compressed segment %s: %d → %d tokens (%.0f%% reduction)",
        segment.id,
        segment.original_tokens,
        new_tokens,
        (1 - new_tokens / segment.original_tokens) * 100 if segment.original_tokens > 0 else 0,
    )

    return segment


async def compress_conversation(
    memory_root: Path,
    conversation: LongConversation,
    openai_base_url: str,
    model: str,
    api_key: str | None = None,
) -> LongConversation:
    """Compress segments until under the threshold.

    Selects segments to compress prioritizing:
    1. Assistant messages (more aggressive compression)
    2. Older messages first
    """
    if not should_compress(conversation):
        return conversation

    # Calculate how many tokens we need to free
    target_tokens = int(conversation.target_context_tokens * conversation.compress_threshold * 0.9)
    tokens_to_free = conversation.current_total_tokens - target_tokens

    LOGGER.info(
        "Conversation %s needs compression: %d tokens, target %d, need to free %d",
        conversation.id,
        conversation.current_total_tokens,
        target_tokens,
        tokens_to_free,
    )

    # Select segments to compress
    segments_to_compress = select_segments_to_compress(conversation, tokens_to_free)

    if not segments_to_compress:
        LOGGER.warning("No segments available for compression")
        return conversation

    # Compress selected segments
    total_saved = 0
    for segment in segments_to_compress:
        old_tokens = segment.current_tokens
        await compress_segment(
            memory_root,
            conversation,
            segment,
            openai_base_url,
            model,
            api_key,
        )
        saved = old_tokens - segment.current_tokens
        total_saved += saved
        conversation.current_total_tokens -= saved

        # Stop if we've freed enough tokens
        if total_saved >= tokens_to_free:
            break

    # Update metadata
    save_conversation_metadata(memory_root, conversation)

    LOGGER.info(
        "Compression complete: freed %d tokens, now at %d (%.1f%% of target)",
        total_saved,
        conversation.current_total_tokens,
        (conversation.current_total_tokens / conversation.target_context_tokens) * 100,
    )

    return conversation


# --- Chat Processing ---


def _extract_assistant_content(response: dict[str, Any]) -> str | None:
    """Extract assistant content from a chat completion response."""
    choices = response.get("choices", [])
    if not choices:
        return None
    message = choices[0].get("message")
    if not message:
        return None
    return message.get("content")


async def process_long_conversation_chat(
    memory_root: Path,
    conversation_id: str,
    messages: list[dict[str, str]],
    model: str,
    openai_base_url: str,
    api_key: str | None = None,
    *,
    stream: bool = False,
    target_context_tokens: int = 150_000,
    compress_threshold: float = 0.8,
    raw_recent_tokens: int = 40_000,
) -> Any:
    """Process a chat request in long conversation mode.

    Maintains chronological context with asymmetric compression:
    - User messages compressed gently (preserve code, quotes)
    - Assistant messages compressed aggressively (bullet points)
    """
    from agent_cli.core.openai_proxy import forward_chat_request  # noqa: PLC0415
    from agent_cli.memory.models import ChatRequest, Message  # noqa: PLC0415

    LOGGER.info("Long conversation chat: conversation=%s, model=%s", conversation_id, model)

    # Load or create conversation
    conversation = load_conversation(
        memory_root,
        conversation_id,
        target_context_tokens=target_context_tokens,
        compress_threshold=compress_threshold,
        raw_recent_tokens=raw_recent_tokens,
    )

    # Extract new user message from request
    user_message = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        LOGGER.warning("No user message found in request")
        # Fall through with empty message

    # Build context using conversation history
    context_messages = build_context(
        conversation,
        new_message=user_message or "",
        token_budget=target_context_tokens,
        system_prompt=None,  # Could extract from messages if present
    )

    # Create augmented request
    aug_messages = [Message(role=m["role"], content=m["content"]) for m in context_messages]
    aug_request = ChatRequest(
        messages=aug_messages,
        model=model,
        stream=stream,
    )

    # Streaming support will be added in Phase 2
    if stream:
        LOGGER.warning(
            "Streaming not yet supported in long conversation mode, falling back to non-streaming",
        )
        aug_request.stream = False

    # Forward to LLM
    response = await forward_chat_request(
        aug_request,
        openai_base_url,
        api_key,
        exclude_fields=set(),
    )

    if not isinstance(response, dict):
        return response

    # Append user message as segment
    if user_message:
        user_segment = create_segment("user", user_message)
        append_segment(memory_root, conversation, user_segment)

    # Append assistant response as segment
    assistant_content = _extract_assistant_content(response)
    if assistant_content:
        assistant_segment = create_segment("assistant", assistant_content)
        append_segment(memory_root, conversation, assistant_segment)

    # Compress if needed (runs in background after returning response)
    if should_compress(conversation):
        LOGGER.info(
            "Conversation %s exceeds compression threshold (%.1f%% of %d tokens), compressing...",
            conversation_id,
            (conversation.current_total_tokens / conversation.target_context_tokens) * 100,
            conversation.target_context_tokens,
        )
        await compress_conversation(
            memory_root,
            conversation,
            openai_base_url,
            model,
            api_key,
        )

    return response
