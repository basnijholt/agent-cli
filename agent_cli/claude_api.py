"""FastAPI web service for remote Claude Code access via Agent SDK."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

# Constants
PROMPT_TRUNCATE_LENGTH = 50

# Default tools allowed for Claude Code operations
DEFAULT_ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
]


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


class SimplePromptRequest(BaseModel):
    """Request model for simplified prompt endpoint."""

    prompt: str
    project: str | None = None  # Optional project name, uses default if not specified


class SimplePromptResponse(BaseModel):
    """Response model for simplified prompt endpoint."""

    summary: str
    files_changed: list[str]
    log_id: str
    log_url: str
    success: bool
    error: str | None = None


class ToolCall(BaseModel):
    """Represents a tool call made during execution."""

    name: str
    input: dict[str, Any]
    file_path: str | None = None


@dataclass
class LogEntry:
    """A log entry for a Claude Code interaction."""

    log_id: str
    project: str
    prompt: str
    summary: str
    files_changed: list[str]
    tool_calls: list[dict[str, Any]]
    full_response: str
    timestamp: datetime
    success: bool
    error: str | None = None


class LogStore:
    """In-memory storage for conversation logs."""

    def __init__(self, max_entries: int = 100) -> None:
        """Initialize the log store."""
        self.entries: dict[str, LogEntry] = {}
        self.max_entries = max_entries

    def add(self, entry: LogEntry) -> None:
        """Add a log entry."""
        # Remove oldest entries if at capacity
        if len(self.entries) >= self.max_entries:
            oldest_id = min(self.entries, key=lambda k: self.entries[k].timestamp)
            del self.entries[oldest_id]
        self.entries[entry.log_id] = entry

    def get(self, log_id: str) -> LogEntry | None:
        """Get a log entry by ID."""
        return self.entries.get(log_id)

    def list_recent(self, limit: int = 20) -> list[LogEntry]:
        """List recent log entries."""
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda e: e.timestamp,
            reverse=True,
        )
        return sorted_entries[:limit]


# Global log store
log_store = LogStore()


@dataclass
class Session:
    """Represents an active Claude Code session."""

    session_id: str
    cwd: Path
    project_name: str | None = None
    cancelled: bool = False
    claude_session_id: str | None = None  # The actual Claude SDK session ID


class SessionManager:
    """Manages active Claude Code sessions."""

    def __init__(self) -> None:
        """Initialize the session manager."""
        self.sessions: dict[str, Session] = {}
        self._project_sessions: dict[str, str] = {}  # project_name -> session_id
        self._cancel_events: dict[str, asyncio.Event] = {}

    def create_session(self, cwd: str = ".", project_name: str | None = None) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            cwd=Path(cwd).resolve(),
            project_name=project_name,
        )
        self.sessions[session_id] = session
        self._cancel_events[session_id] = asyncio.Event()
        if project_name:
            self._project_sessions[project_name] = session_id
        LOGGER.info(
            "Created session %s with cwd=%s project=%s",
            session_id,
            session.cwd,
            project_name,
        )
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def get_or_create_project_session(self, project_name: str, cwd: str) -> Session:
        """Get existing session for project or create a new one."""
        if project_name in self._project_sessions:
            session_id = self._project_sessions[project_name]
            session = self.sessions.get(session_id)
            if session:
                return session
        return self.create_session(cwd=cwd, project_name=project_name)

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
        session = self.sessions.pop(session_id, None)
        if session and session.project_name:
            self._project_sessions.pop(session.project_name, None)
        self._cancel_events.pop(session_id, None)


class ProjectManager:
    """Manages named projects and the current/default project."""

    def __init__(self) -> None:
        """Initialize the project manager."""
        self.projects: dict[str, str] = {}  # name -> path
        self.default_project: str | None = None
        self.current_project: str | None = None  # Sticky session support

    def configure(self, projects: dict[str, str], default: str | None = None) -> None:
        """Configure projects from settings."""
        self.projects = projects
        self.default_project = default
        if default and not self.current_project:
            self.current_project = default

    def get_project_path(self, project_name: str) -> str | None:
        """Get the path for a project."""
        return self.projects.get(project_name)

    def resolve_project(
        self,
        prompt: str,
        explicit_project: str | None = None,
    ) -> tuple[str, str, str]:
        """Resolve which project to use and clean the prompt.

        Returns: (project_name, project_path, cleaned_prompt)
        """
        # 1. Check for explicit project parameter
        if explicit_project:
            path = self.get_project_path(explicit_project)
            if path:
                self.current_project = explicit_project
                return explicit_project, path, prompt
            msg = f"Unknown project: {explicit_project}"
            raise ValueError(msg)

        # 2. Check for "in {project}," prefix in prompt
        match = re.match(r"^[Ii]n\s+([\w-]+)[,:]?\s*(.*)$", prompt)
        if match:
            project_name = match.group(1).lower()
            cleaned_prompt = match.group(2)
            path = self.get_project_path(project_name)
            if path:
                self.current_project = project_name
                return project_name, path, cleaned_prompt

        # 3. Use current/sticky project
        if self.current_project:
            path = self.get_project_path(self.current_project)
            if path:
                return self.current_project, path, prompt

        # 4. Use default project
        if self.default_project:
            path = self.get_project_path(self.default_project)
            if path:
                self.current_project = self.default_project
                return self.default_project, path, prompt

        msg = "No project specified and no default project configured"
        raise ValueError(msg)

    def switch_project(self, project_name: str) -> str:
        """Switch the current project."""
        path = self.get_project_path(project_name)
        if not path:
            msg = f"Unknown project: {project_name}"
            raise ValueError(msg)
        self.current_project = project_name
        return path


# Global managers
session_manager = SessionManager()
project_manager = ProjectManager()

# FastAPI app
app = FastAPI(
    title="Claude Code Remote API",
    description="Remote access to Claude Code via Agent SDK",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event() -> None:
    """Configure project manager from environment variables on startup."""
    # Read projects from environment (set by CLI)
    projects_json = os.environ.get("CLAUDE_API_PROJECTS")
    default_project = os.environ.get("CLAUDE_API_DEFAULT_PROJECT")

    if projects_json:
        try:
            projects = json.loads(projects_json)
            project_manager.configure(projects, default_project)
            LOGGER.info(
                "Configured projects: %s (default: %s)",
                list(projects.keys()),
                default_project,
            )
        except json.JSONDecodeError:
            LOGGER.warning("Failed to parse CLAUDE_API_PROJECTS environment variable")


def _build_options(session: Session) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions for a session."""
    options = ClaudeAgentOptions(
        cwd=str(session.cwd),
        permission_mode="bypassPermissions",
        allowed_tools=DEFAULT_ALLOWED_TOOLS,
    )
    if session.claude_session_id:
        options.resume = session.claude_session_id
    return options


def _extract_file_changes(tool_calls: list[dict[str, Any]]) -> list[str]:
    """Extract list of changed files from tool calls."""
    files = set()
    for call in tool_calls:
        name = call.get("name", "")
        input_data = call.get("input", {})
        if name in ("Edit", "Write", "MultiEdit"):
            file_path = input_data.get("file_path")
            if file_path:
                files.add(file_path)
        elif name == "Bash":
            # Check for common file-modifying commands
            cmd = input_data.get("command", "")
            if any(op in cmd for op in ["mv ", "cp ", "rm ", "touch ", "mkdir "]):
                # Can't reliably extract file paths, but note the command type
                pass
    return sorted(files)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/prompt", response_model=SimplePromptResponse)
async def simple_prompt(  # noqa: PLR0912
    request: SimplePromptRequest,
    req: Request,
) -> SimplePromptResponse:
    """Simplified prompt endpoint with automatic project/session management.

    Supports:
    - Explicit project parameter: {"prompt": "...", "project": "my-project"}
    - Project prefix in prompt: "In my-project, fix the bug"
    - Sticky sessions: remembers last used project
    - Default project from config
    """
    try:
        # Resolve project
        project_name, project_path, cleaned_prompt = project_manager.resolve_project(
            request.prompt,
            request.project,
        )
    except ValueError as e:
        return SimplePromptResponse(
            summary="",
            files_changed=[],
            log_id="",
            log_url="",
            success=False,
            error=str(e),
        )

    # Get or create session for this project
    session = session_manager.get_or_create_project_session(project_name, project_path)

    try:
        summary = ""
        full_response = ""
        tool_calls: list[dict[str, Any]] = []
        session.cancelled = False
        options = _build_options(session)

        async for message in query(prompt=cleaned_prompt, options=options):
            if session.cancelled:
                break

            if isinstance(message, SystemMessage):
                if message.subtype == "init":
                    init_session_id = message.data.get("session_id")
                    if init_session_id:
                        session.claude_session_id = init_session_id

            elif isinstance(message, ResultMessage):
                if message.result:
                    summary = message.result

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        full_response += block.text
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(
                            {
                                "name": block.name,
                                "input": block.input,
                            },
                        )

        # Extract file changes
        files_changed = _extract_file_changes(tool_calls)

        # Generate log entry
        log_id = str(uuid.uuid4())[:8]
        base_url = str(req.base_url).rstrip("/")
        log_url = f"{base_url}/log/{log_id}"

        # Store log entry
        log_entry = LogEntry(
            log_id=log_id,
            project=project_name,
            prompt=request.prompt,
            summary=summary or full_response[:200],
            files_changed=files_changed,
            tool_calls=tool_calls,
            full_response=full_response,
            timestamp=datetime.now(UTC),
            success=True,
        )
        log_store.add(log_entry)

        return SimplePromptResponse(
            summary=summary or full_response[:200],
            files_changed=files_changed,
            log_id=log_id,
            log_url=log_url,
            success=True,
        )

    except Exception as e:
        LOGGER.exception("Error during Claude Code query")
        return SimplePromptResponse(
            summary="",
            files_changed=[],
            log_id="",
            log_url="",
            success=False,
            error=str(e),
        )


@app.get("/log/{log_id}", response_class=HTMLResponse)
async def view_log(log_id: str) -> HTMLResponse:
    """View log entry details in a web UI."""
    entry = log_store.get(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Log entry not found")

    # Generate HTML page
    files_html = (
        "".join(f"<li>{f}</li>" for f in entry.files_changed) or "<li>No files changed</li>"
    )
    tools_html = (
        "".join(
            f"<li><strong>{t['name']}</strong>: {t.get('input', {}).get('file_path', 'N/A')}</li>"
            for t in entry.tool_calls
        )
        or "<li>No tool calls</li>"
    )

    html = f"""
    <!DOCTYPE html>
    <html data-theme="dark">
    <head>
        <title>Claude Code Log - {log_id}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-base-200 p-4 md:p-8">
        <div class="max-w-3xl mx-auto space-y-6">
            <div class="flex items-center gap-4">
                <h1 class="text-2xl font-bold">🤖 Claude Code Log</h1>
                <a href="/logs" class="btn btn-ghost btn-sm">← All Logs</a>
            </div>

            <div class="flex flex-wrap gap-2 items-center">
                <span class="badge {"badge-error" if not entry.success else "badge-success"} gap-1">
                    {"❌ Error" if not entry.success else "✅ Success"}
                </span>
                <span class="badge badge-outline">{entry.project}</span>
                <span class="text-sm opacity-60">{entry.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}</span>
            </div>

            <div class="card bg-base-100 shadow">
                <div class="card-body">
                    <h2 class="card-title text-sm opacity-60">📝 Prompt</h2>
                    <p>{entry.prompt}</p>
                </div>
            </div>

            <div class="card bg-base-100 shadow border-l-4 border-primary">
                <div class="card-body">
                    <h2 class="card-title text-sm opacity-60">💬 Summary</h2>
                    <p>{entry.summary}</p>
                </div>
            </div>

            <div class="grid md:grid-cols-2 gap-4">
                <div class="card bg-base-100 shadow">
                    <div class="card-body">
                        <h2 class="card-title text-sm opacity-60">📁 Files Changed ({len(entry.files_changed)})</h2>
                        <ul class="menu bg-base-200 rounded-box">{files_html}</ul>
                    </div>
                </div>
                <div class="card bg-base-100 shadow">
                    <div class="card-body">
                        <h2 class="card-title text-sm opacity-60">🔧 Tool Calls ({len(entry.tool_calls)})</h2>
                        <ul class="menu bg-base-200 rounded-box">{tools_html}</ul>
                    </div>
                </div>
            </div>

            <div class="collapse collapse-arrow bg-base-100 shadow">
                <input type="checkbox" />
                <div class="collapse-title font-medium">📄 Full Response</div>
                <div class="collapse-content">
                    <pre class="bg-base-200 p-4 rounded-box overflow-auto max-h-96 text-sm">{entry.full_response or "(No text response)"}</pre>
                </div>
            </div>

            {f'<div class="alert alert-error"><span>❌ {entry.error}</span></div>' if entry.error else ""}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


def _truncate_prompt(prompt: str) -> str:
    """Truncate prompt for display."""
    if len(prompt) > PROMPT_TRUNCATE_LENGTH:
        return prompt[:PROMPT_TRUNCATE_LENGTH] + "..."
    return prompt


@app.get("/logs", response_class=HTMLResponse)
async def list_logs() -> HTMLResponse:
    """List recent log entries."""
    entries = log_store.list_recent(20)

    rows = (
        "".join(
            f"""<tr class="hover">
            <td><a href="/log/{e.log_id}" class="link link-primary">{e.log_id}</a></td>
            <td><span class="badge badge-ghost">{e.project}</span></td>
            <td class="max-w-xs truncate">{_truncate_prompt(e.prompt)}</td>
            <td><span class="badge badge-sm">{len(e.files_changed)}</span></td>
            <td>{"<span class='badge badge-success badge-sm'>✓</span>" if e.success else "<span class='badge badge-error badge-sm'>✗</span>"}</td>
            <td class="text-sm opacity-60">{e.timestamp.strftime("%H:%M:%S")}</td>
        </tr>"""
            for e in entries
        )
        or "<tr><td colspan='6' class='text-center opacity-60'>No logs yet</td></tr>"
    )

    html = f"""
    <!DOCTYPE html>
    <html data-theme="dark">
    <head>
        <title>Claude Code Logs</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-base-200 p-4 md:p-8">
        <div class="max-w-4xl mx-auto space-y-6">
            <h1 class="text-2xl font-bold">🤖 Claude Code Logs</h1>

            <div class="overflow-x-auto">
                <table class="table table-zebra bg-base-100 shadow rounded-box">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Project</th>
                            <th>Prompt</th>
                            <th>Files</th>
                            <th>Status</th>
                            <th>Time</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page() -> HTMLResponse:
    """Interactive chat page with HTMX and voice input support."""
    # Build project options HTML
    projects = project_manager.projects
    current = project_manager.current_project or project_manager.default_project or ""
    project_options = "".join(
        f'<option value="{name}"{" selected" if name == current else ""}>{name}</option>'
        for name in projects
    )

    html = f"""
    <!DOCTYPE html>
    <html data-theme="dark">
    <head>
        <title>Claude Code Chat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/daisyui@4/dist/full.min.css" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    </head>
    <body class="min-h-screen bg-base-200">
        <div class="flex flex-col h-screen max-w-3xl mx-auto">
            <!-- Header -->
            <div class="navbar bg-base-100 shadow">
                <div class="flex-1">
                    <a href="/logs" class="btn btn-ghost">🤖 Claude Code</a>
                </div>
                <div class="flex-none gap-2">
                    <select id="project" name="project" class="select select-bordered select-sm">
                        {project_options}
                    </select>
                    <input type="text" id="voiceServer" placeholder="Voice server URL"
                           class="input input-bordered input-sm w-48"
                           value="http://localhost:8000">
                </div>
            </div>

            <!-- Messages (loaded via HTMX on page load) -->
            <div id="messages" class="flex-1 overflow-y-auto p-4 space-y-4"
                 hx-get="/chat/messages"
                 hx-trigger="load"
                 hx-swap="innerHTML">
                <div class="text-center opacity-60 py-8">Loading...</div>
            </div>

            <!-- Input Form with HTMX -->
            <form id="chatForm" class="p-4 bg-base-100 border-t border-base-300"
                  hx-post="/chat/send"
                  hx-target="#messages"
                  hx-swap="beforeend scroll:#messages:bottom"
                  hx-indicator="#loading"
                  hx-on::after-request="this.reset()">
                <div class="flex gap-2">
                    <button type="button" id="micBtn" class="btn btn-circle btn-outline" title="Hold to record">
                        🎤
                    </button>
                    <button type="button" id="permBtn" class="btn btn-sm btn-ghost hidden" onclick="requestMicPermission()">
                        🔓 Allow mic
                    </button>
                    <input type="hidden" name="project" id="projectInput" value="{current}">
                    <input type="text" name="prompt" id="prompt" placeholder="Type or hold mic to speak..."
                           class="input input-bordered flex-1" autocomplete="off">
                    <button type="submit" class="btn btn-primary">
                        <span id="loading" class="loading loading-spinner htmx-indicator"></span>
                        Send
                    </button>
                </div>
                <div id="status" class="text-sm opacity-60 mt-2 hidden"></div>
            </form>
        </div>

        <script>
        // Sync project selector with hidden form input
        document.getElementById('project').onchange = function() {{
            document.getElementById('projectInput').value = this.value;
        }};

        // Scroll to bottom after HTMX swaps
        document.body.addEventListener('htmx:afterSwap', function(e) {{
            if (e.detail.target.id === 'messages') {{
                e.detail.target.scrollTop = e.detail.target.scrollHeight;
            }}
        }});

        // Voice recording (minimal JS - only for MediaRecorder API)
        const micBtn = document.getElementById('micBtn');
        const permBtn = document.getElementById('permBtn');
        let mediaRecorder = null;
        let audioChunks = [];
        let micPermissionGranted = false;

        function setStatus(msg, show=true) {{
            const el = document.getElementById('status');
            el.textContent = msg;
            el.classList.toggle('hidden', !show);
        }}

        const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
        if (!hasMediaDevices) {{
            micBtn.disabled = true;
            micBtn.title = 'Voice requires HTTPS';
            micBtn.classList.add('btn-disabled');
        }}

        async function requestMicPermission() {{
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{audio: true}});
                stream.getTracks().forEach(t => t.stop());
                micPermissionGranted = true;
                permBtn.classList.add('hidden');
                micBtn.classList.remove('btn-disabled');
                setStatus('✅ Mic access granted. Hold 🎤 to record.');
            }} catch (e) {{
                setStatus('❌ Mic denied. Check browser settings.');
            }}
        }}

        if (hasMediaDevices && navigator.permissions?.query) {{
            navigator.permissions.query({{name: 'microphone'}}).then(r => {{
                if (r.state === 'granted') micPermissionGranted = true;
                else if (r.state === 'prompt') {{
                    permBtn.classList.remove('hidden');
                    setStatus('👆 Tap "Allow mic" first');
                }}
            }}).catch(() => permBtn.classList.remove('hidden'));
        }} else if (hasMediaDevices) {{
            permBtn.classList.remove('hidden');
        }}

        micBtn.onmousedown = micBtn.ontouchstart = async (e) => {{
            e.preventDefault();
            if (!hasMediaDevices || !micPermissionGranted) {{
                setStatus('👆 Tap "Allow mic" first');
                permBtn.classList.remove('hidden');
                return;
            }}
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{audio: true}});
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];
                mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
                mediaRecorder.start();
                micBtn.classList.add('btn-error');
                setStatus('🎤 Recording...');
            }} catch (e) {{
                setStatus('Mic error: ' + e.message);
                micPermissionGranted = false;
                permBtn.classList.remove('hidden');
            }}
        }};

        micBtn.onmouseup = micBtn.ontouchend = micBtn.onmouseleave = async () => {{
            if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
            mediaRecorder.stop();
            micBtn.classList.remove('btn-error');
            setStatus('Transcribing...');

            mediaRecorder.onstop = async () => {{
                const blob = new Blob(audioChunks, {{type: 'audio/webm'}});
                const formData = new FormData();
                formData.append('audio', blob, 'recording.webm');
                try {{
                    const voiceUrl = document.getElementById('voiceServer').value;
                    const resp = await fetch(voiceUrl + '/transcribe', {{method: 'POST', body: formData}});
                    const data = await resp.json();
                    setStatus('', false);
                    const text = data.cleaned_transcript || data.raw_transcript || data.transcript || '';
                    if (text) document.getElementById('prompt').value = text;
                    else setStatus('No speech detected');
                }} catch (e) {{
                    setStatus('Transcription error: ' + e.message);
                }}
                mediaRecorder.stream.getTracks().forEach(t => t.stop());
            }};
        }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/logs/json")
async def list_logs_json(limit: int = 20) -> list[dict[str, Any]]:
    """List recent log entries as JSON for chat history."""
    entries = log_store.list_recent(limit)
    return [
        {
            "log_id": e.log_id,
            "project": e.project,
            "prompt": e.prompt,
            "summary": e.summary,
            "files_changed": e.files_changed,
            "success": e.success,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in entries
    ]


def _render_message(
    role: str,
    content: str,
    files_changed: list[str] | None = None,
    log_id: str | None = None,
) -> str:
    """Render a single chat message as HTML."""
    chat_class = "chat chat-end" if role == "user" else "chat chat-start"
    bubble_class = "chat-bubble-primary" if role == "user" else ""

    meta_html = ""
    if files_changed:
        meta_html += f'<div class="text-xs opacity-60 mt-1">📁 {", ".join(files_changed)}</div>'
    if log_id:
        meta_html += f'<a href="/log/{log_id}" class="link link-primary text-xs">View details →</a>'

    return f"""<div class="{chat_class}">
        <div class="chat-bubble {bubble_class}">{content}{meta_html}</div>
    </div>"""


@app.get("/chat/messages", response_class=HTMLResponse)
async def chat_messages() -> HTMLResponse:
    """Return chat history as HTML fragments for HTMX."""
    entries = log_store.list_recent(20)
    if not entries:
        return HTMLResponse(content="")

    # Reverse to show oldest first
    html_parts = []
    for entry in reversed(entries):
        html_parts.append(_render_message("user", entry.prompt))
        html_parts.append(
            _render_message(
                "assistant",
                entry.summary,
                entry.files_changed,
                entry.log_id,
            ),
        )
    return HTMLResponse(content="\n".join(html_parts))


class ChatSendRequest(BaseModel):
    """Form data for chat send endpoint."""

    prompt: str
    project: str | None = None


@app.post("/chat/send", response_class=HTMLResponse)
async def chat_send(request: Request) -> HTMLResponse:
    """Send a message and return HTML fragments for HTMX."""
    # Parse form data
    form = await request.form()
    prompt = str(form.get("prompt", "")).strip()
    project = str(form.get("project", "")) or None

    if not prompt:
        return HTMLResponse(content="")

    # Render user message immediately
    user_html = _render_message("user", prompt)

    try:
        # Resolve project
        project_name, project_path, cleaned_prompt = project_manager.resolve_project(
            prompt,
            project,
        )
    except ValueError as e:
        error_html = _render_message("assistant", f"❌ Error: {e}")
        return HTMLResponse(content=user_html + error_html)

    # Get or create session
    session = session_manager.get_or_create_project_session(project_name, project_path)

    try:
        summary = ""
        full_response = ""
        tool_calls: list[dict[str, Any]] = []
        session.cancelled = False
        options = _build_options(session)

        async for message in query(prompt=cleaned_prompt, options=options):
            if session.cancelled:
                break

            if isinstance(message, SystemMessage) and message.subtype == "init":
                session.claude_session_id = message.data.get("session_id")
            elif isinstance(message, ResultMessage) and message.result:
                summary = message.result
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        full_response += block.text
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append({"name": block.name, "input": block.input})

        # Extract file changes and store log
        files_changed = _extract_file_changes(tool_calls)
        log_id = str(uuid.uuid4())[:8]

        log_entry = LogEntry(
            log_id=log_id,
            project=project_name,
            prompt=prompt,
            summary=summary or full_response[:200],
            files_changed=files_changed,
            tool_calls=tool_calls,
            full_response=full_response,
            timestamp=datetime.now(UTC),
            success=True,
        )
        log_store.add(log_entry)

        assistant_html = _render_message(
            "assistant",
            summary or full_response[:200],
            files_changed,
            log_id,
        )
        return HTMLResponse(content=user_html + assistant_html)

    except Exception as e:
        LOGGER.exception("Error during chat send")
        error_html = _render_message("assistant", f"❌ Error: {e}")
        return HTMLResponse(content=user_html + error_html)


@app.post("/transcribe-proxy")
async def transcribe_proxy(request: Request) -> dict[str, Any]:
    """Proxy transcription requests to avoid CORS issues."""
    # Get voice server URL from query param or use default
    voice_server = request.query_params.get("voice_server", "http://localhost:61337")

    # Forward the multipart form data
    body = await request.body()
    content_type = request.headers.get("content-type", "")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{voice_server}/transcribe",
                content=body,
                headers={"content-type": content_type},
            )
            return resp.json()
    except Exception as e:
        LOGGER.exception("Transcription proxy error")
        return {"error": str(e), "raw_transcript": "", "cleaned_transcript": ""}


@app.post("/switch-project")
async def switch_project(project: str) -> dict[str, str]:
    """Switch the current/sticky project."""
    try:
        path = project_manager.switch_project(project)
        return {"status": "switched", "project": project, "path": path}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/projects")
async def list_projects() -> dict[str, Any]:
    """List configured projects."""
    return {
        "projects": project_manager.projects,
        "default": project_manager.default_project,
        "current": project_manager.current_project,
    }


@app.post("/session/new", response_model=NewSessionResponse)
async def create_session(request: NewSessionRequest) -> NewSessionResponse:
    """Create a new Claude Code session."""
    session = session_manager.create_session(cwd=request.cwd)
    return NewSessionResponse(session_id=session.session_id, status="created")


@app.post("/session/{session_id}/prompt", response_model=PromptResponse)
async def send_prompt(session_id: str, request: PromptRequest) -> PromptResponse:
    """Send a prompt to Claude Code and get the result."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        result_text = ""
        session.cancelled = False
        options = _build_options(session)

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
    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "error": "Session not found"})
        await websocket.close(code=4004)
        return

    try:
        while True:
            # Wait for prompt from client
            data = await websocket.receive_json()
            prompt = data.get("prompt", "")

            if not prompt:
                await websocket.send_json({"type": "error", "error": "No prompt provided"})
                continue

            session.cancelled = False
            options = _build_options(session)

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
