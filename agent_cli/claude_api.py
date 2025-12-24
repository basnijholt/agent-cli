"""FastAPI web service for remote Claude Code access via Agent SDK."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


# Pydantic models for request/response
class NewSessionRequest(BaseModel):
    """Request model for creating a new session."""

    cwd: str = "."


class NewSessionResponse(BaseModel):
    """Response model for session creation."""

    session_id: str
    status: str = "created"


class PromptRequest(BaseModel):
    """Request model for sending a prompt."""

    prompt: str


class PromptResponse(BaseModel):
    """Response model for prompt results."""

    result: str
    success: bool
    error: str | None = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str


@dataclass
class Session:
    """Represents an active Claude Code session."""

    session_id: str
    cwd: Path
    cancelled: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    claude_session_id: str | None = None  # The actual Claude SDK session ID


class SessionManager:
    """Manages active Claude Code sessions."""

    def __init__(self) -> None:
        """Initialize the session manager."""
        self.sessions: dict[str, Session] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def create_session(self, cwd: str = ".") -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id, cwd=Path(cwd).resolve())
        self.sessions[session_id] = session
        self._cancel_events[session_id] = asyncio.Event()
        LOGGER.info("Created session %s with cwd=%s", session_id, session.cwd)
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def cancel_session(self, session_id: str) -> bool:
        """Mark a session as cancelled."""
        if session_id in self.sessions:
            self.sessions[session_id].cancelled = True
            if session_id in self._cancel_events:
                self._cancel_events[session_id].set()
            return True
        return False

    def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        self.sessions.pop(session_id, None)
        self._cancel_events.pop(session_id, None)


# Global session manager
session_manager = SessionManager()

# FastAPI app
app = FastAPI(
    title="Claude Code Remote API",
    description="Remote access to Claude Code via Agent SDK",
    version="1.0.0",
)


def _check_claude_sdk() -> None:
    """Check if claude-agent-sdk is available."""
    try:
        import claude_agent_sdk  # noqa: F401, PLC0415
    except ImportError as e:
        msg = (
            "claude-agent-sdk is not installed. "
            "Please install it with: pip install agent-cli[claude]"
        )
        raise ImportError(msg) from e


def _get_sdk_types() -> tuple[type, ...]:
    """Import and return SDK message types."""
    from claude_agent_sdk.types import (  # noqa: PLC0415
        AssistantMessage,
        ResultMessage,
        StreamEvent,
        SystemMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )

    return (
        UserMessage,
        AssistantMessage,
        SystemMessage,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
    )


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/session/new", response_model=NewSessionResponse)
async def create_session(request: NewSessionRequest) -> NewSessionResponse:
    """Create a new Claude Code session."""
    _check_claude_sdk()
    session = session_manager.create_session(cwd=request.cwd)
    return NewSessionResponse(session_id=session.session_id, status="created")


@app.post("/session/{session_id}/prompt", response_model=PromptResponse)
async def send_prompt(session_id: str, request: PromptRequest) -> PromptResponse:  # noqa: PLR0912
    """Send a prompt to Claude Code and get the result."""
    _check_claude_sdk()

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, query  # noqa: PLC0415
        from claude_agent_sdk.types import (  # noqa: PLC0415
            AssistantMessage,
            ResultMessage,
            SystemMessage,
            TextBlock,
        )

        result_text = ""
        session.cancelled = False

        # Build options - only use resume if we have a valid Claude session ID
        options = ClaudeAgentOptions(
            cwd=str(session.cwd),
            permission_mode="bypassPermissions",
            allowed_tools=[
                "Read",
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
            ],
        )

        # Resume existing Claude session if available
        if session.claude_session_id:
            options.resume = session.claude_session_id

        async for message in query(prompt=request.prompt, options=options):
            if session.cancelled:
                break

            # Handle different message types with proper isinstance checks
            if isinstance(message, SystemMessage):
                if message.subtype == "init":
                    # Extract session_id from data dict
                    init_session_id = message.data.get("session_id")
                    if init_session_id:
                        session.claude_session_id = init_session_id
                        LOGGER.info(
                            "Captured Claude session ID: %s",
                            session.claude_session_id,
                        )

            elif isinstance(message, ResultMessage):
                if message.result:
                    result_text = message.result

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        return PromptResponse(result=result_text, success=True)

    except Exception as e:
        LOGGER.exception("Error during Claude Code query")
        return PromptResponse(result="", success=False, error=str(e))


@app.post("/session/{session_id}/cancel")
async def cancel_session(session_id: str) -> dict[str, str]:
    """Cancel the current operation in a session."""
    if session_manager.cancel_session(session_id):
        return {"status": "cancelled"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.websocket("/session/{session_id}/stream")
async def stream_session(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for streaming Claude Code responses."""
    _check_claude_sdk()

    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "error": "Session not found"})
        await websocket.close(code=4004)
        return

    try:
        from claude_agent_sdk import ClaudeAgentOptions, query  # noqa: PLC0415
        from claude_agent_sdk.types import (  # noqa: PLC0415
            AssistantMessage,
            ResultMessage,
            SystemMessage,
            TextBlock,
            ThinkingBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        while True:
            # Wait for prompt from client
            data = await websocket.receive_json()
            prompt = data.get("prompt", "")

            if not prompt:
                await websocket.send_json({"type": "error", "error": "No prompt provided"})
                continue

            session.cancelled = False

            # Build options
            options = ClaudeAgentOptions(
                cwd=str(session.cwd),
                permission_mode="bypassPermissions",
                allowed_tools=[
                    "Read",
                    "Write",
                    "Edit",
                    "Bash",
                    "Glob",
                    "Grep",
                    "WebSearch",
                    "WebFetch",
                ],
            )

            if session.claude_session_id:
                options.resume = session.claude_session_id

            try:
                async for message in query(prompt=prompt, options=options):
                    if session.cancelled:
                        await websocket.send_json({"type": "cancelled"})
                        break

                    # Convert message to JSON with proper type checks
                    msg_dict = _message_to_dict(
                        message,
                        session,
                        SystemMessage,
                        ResultMessage,
                        AssistantMessage,
                        TextBlock,
                        ThinkingBlock,
                        ToolUseBlock,
                        ToolResultBlock,
                    )
                    if msg_dict:
                        await websocket.send_json(msg_dict)

                await websocket.send_json({"type": "done"})

            except Exception as e:
                LOGGER.exception("Error during streaming")
                await websocket.send_json({"type": "error", "error": str(e)})

    except WebSocketDisconnect:
        LOGGER.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        LOGGER.exception("WebSocket error")
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "error": str(e)})


def _message_to_dict(
    message: Any,
    session: Session,
    system_msg_type: type,
    result_msg_type: type,
    assistant_msg_type: type,
    text_block_type: type,
    thinking_block_type: type,
    tool_use_block_type: type,
    tool_result_block_type: type,
) -> dict[str, Any] | None:
    """Convert a Claude SDK message to a JSON-serializable dict."""
    if isinstance(message, system_msg_type):
        if message.subtype == "init":  # type: ignore[attr-defined]
            init_session_id = message.data.get("session_id")  # type: ignore[attr-defined]
            if init_session_id:
                session.claude_session_id = init_session_id
            return {"type": "init", "session_id": init_session_id}
        return None

    if isinstance(message, result_msg_type):
        return {
            "type": "result",
            "subtype": message.subtype,  # type: ignore[attr-defined]
            "result": message.result or "",  # type: ignore[attr-defined]
        }

    if isinstance(message, assistant_msg_type):
        blocks = []
        for block in message.content:  # type: ignore[attr-defined]
            if isinstance(block, text_block_type):
                blocks.append({"type": "text", "text": block.text})  # type: ignore[attr-defined]
            elif isinstance(block, thinking_block_type):
                blocks.append({"type": "thinking", "thinking": block.thinking})  # type: ignore[attr-defined]
            elif isinstance(block, tool_use_block_type):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,  # type: ignore[attr-defined]
                        "name": block.name,  # type: ignore[attr-defined]
                        "input": block.input,  # type: ignore[attr-defined]
                    },
                )
            elif isinstance(block, tool_result_block_type):
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,  # type: ignore[attr-defined]
                        "content": block.content,  # type: ignore[attr-defined]
                    },
                )
        if blocks:
            return {"type": "assistant", "content": blocks}
        return None

    return None
