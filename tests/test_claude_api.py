"""Tests for the Claude Code remote API."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_claude_sdk() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Mock the claude_agent_sdk module."""
    mock_sdk = MagicMock()
    mock_sdk.ClaudeAgentOptions = MagicMock

    # Mock types
    mock_types = MagicMock()
    mock_types.SystemMessage = type("SystemMessage", (), {})
    mock_types.AssistantMessage = type("AssistantMessage", (), {})
    mock_types.ResultMessage = type("ResultMessage", (), {})
    mock_types.TextBlock = type("TextBlock", (), {})
    mock_types.ThinkingBlock = type("ThinkingBlock", (), {})
    mock_types.ToolUseBlock = type("ToolUseBlock", (), {})
    mock_types.ToolResultBlock = type("ToolResultBlock", (), {})

    with (
        patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}),
        patch.dict("sys.modules", {"claude_agent_sdk.types": mock_types}),
    ):
        yield mock_sdk, mock_types


@pytest.fixture
def client(mock_claude_sdk: Any) -> TestClient:  # noqa: ARG001
    """Create a test client for the Claude API app."""
    from agent_cli.claude_api import app  # noqa: PLC0415

    return TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Test the health check endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"


class TestSessionManagement:
    """Tests for session creation and management."""

    def test_create_session_default_cwd(self, client: TestClient) -> None:
        """Test creating a session with default working directory."""
        response = client.post("/session/new", json={})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "created"

    def test_create_session_custom_cwd(self, client: TestClient) -> None:
        """Test creating a session with custom working directory."""
        response = client.post("/session/new", json={"cwd": "/tmp"})  # noqa: S108
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "created"

    def test_cancel_nonexistent_session(self, client: TestClient) -> None:
        """Test cancelling a session that doesn't exist."""
        response = client.post("/session/nonexistent-id/cancel")
        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    def test_cancel_existing_session(self, client: TestClient) -> None:
        """Test cancelling an existing session."""
        # First create a session
        create_response = client.post("/session/new", json={})
        session_id = create_response.json()["session_id"]

        # Then cancel it
        cancel_response = client.post(f"/session/{session_id}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] == "cancelled"


class TestPromptEndpoint:
    """Tests for the prompt endpoint."""

    def test_prompt_nonexistent_session(self, client: TestClient) -> None:
        """Test sending prompt to nonexistent session."""
        response = client.post(
            "/session/nonexistent-id/prompt",
            json={"prompt": "Hello"},
        )
        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]


class TestSessionManagerUnit:
    """Unit tests for the SessionManager class."""

    def test_create_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test session creation."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        session = manager.create_session(cwd="/tmp")  # noqa: S108

        assert session.session_id is not None
        assert str(session.cwd) == "/tmp"  # noqa: S108
        assert session.cancelled is False
        assert session.claude_session_id is None

    def test_get_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test retrieving a session."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        created = manager.create_session()

        retrieved = manager.get_session(created.session_id)
        assert retrieved is not None
        assert retrieved.session_id == created.session_id

    def test_get_nonexistent_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test retrieving a session that doesn't exist."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        assert manager.get_session("nonexistent") is None

    def test_cancel_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test cancelling a session."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        session = manager.create_session()

        assert manager.cancel_session(session.session_id) is True
        assert session.cancelled is True

    def test_cancel_nonexistent_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test cancelling a session that doesn't exist."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        assert manager.cancel_session("nonexistent") is False

    def test_remove_session(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test removing a session."""
        from agent_cli.claude_api import SessionManager  # noqa: PLC0415

        manager = SessionManager()
        session = manager.create_session()
        session_id = session.session_id

        manager.remove_session(session_id)
        assert manager.get_session(session_id) is None


class TestBuildOptions:
    """Tests for the _build_options helper."""

    def test_build_options_without_resume(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test building options for a new session without existing Claude session."""
        from agent_cli.claude_api import Session, _build_options  # noqa: PLC0415

        session = Session(session_id="test-id", cwd=Path("/tmp"))  # noqa: S108
        # Session has no claude_session_id, so resume should not be set
        assert session.claude_session_id is None

        options = _build_options(session)
        assert options.cwd == "/tmp"  # noqa: S108
        assert options.permission_mode == "bypassPermissions"
        # With MagicMock, we can't easily check resume wasn't set,
        # but we verify the logic path via session.claude_session_id being None

    def test_build_options_with_resume(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test building options for an existing Claude session."""
        from agent_cli.claude_api import Session, _build_options  # noqa: PLC0415

        session = Session(
            session_id="test-id",
            cwd=Path("/tmp"),  # noqa: S108
            claude_session_id="claude-session-123",
        )
        options = _build_options(session)

        assert options.resume == "claude-session-123"


class TestDefaultAllowedTools:
    """Tests for the default allowed tools constant."""

    def test_default_tools_defined(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test that default allowed tools are defined."""
        from agent_cli.claude_api import DEFAULT_ALLOWED_TOOLS  # noqa: PLC0415

        assert isinstance(DEFAULT_ALLOWED_TOOLS, list)
        assert len(DEFAULT_ALLOWED_TOOLS) > 0

    def test_default_tools_contains_essentials(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test that essential tools are in the default list."""
        from agent_cli.claude_api import DEFAULT_ALLOWED_TOOLS  # noqa: PLC0415

        essential_tools = ["Read", "Write", "Edit", "Bash"]
        for tool in essential_tools:
            assert tool in DEFAULT_ALLOWED_TOOLS


class TestProjectManager:
    """Tests for the ProjectManager class."""

    def test_configure_projects(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test configuring projects."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure(
            {"proj1": "/path/to/proj1", "proj2": "/path/to/proj2"},
            default="proj1",
        )

        assert manager.projects == {"proj1": "/path/to/proj1", "proj2": "/path/to/proj2"}
        assert manager.default_project == "proj1"
        assert manager.current_project == "proj1"

    def test_get_project_path(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test getting project path."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure({"myproject": "/path/to/myproject"})

        assert manager.get_project_path("myproject") == "/path/to/myproject"
        assert manager.get_project_path("unknown") is None

    def test_resolve_project_explicit(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test resolving project with explicit parameter."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure({"proj1": "/path/1", "proj2": "/path/2"}, default="proj1")

        name, path, prompt = manager.resolve_project("do something", explicit_project="proj2")
        assert name == "proj2"
        assert path == "/path/2"
        assert prompt == "do something"

    def test_resolve_project_from_prompt_prefix(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test resolving project from 'in {project},' prefix in prompt."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure({"myproject": "/path/to/myproject"})

        name, path, prompt = manager.resolve_project("in myproject, fix the bug")
        assert name == "myproject"
        assert path == "/path/to/myproject"
        assert prompt == "fix the bug"

    def test_resolve_project_sticky(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test sticky project session."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure({"proj1": "/path/1", "proj2": "/path/2"})

        # First call sets current project
        manager.resolve_project("task", explicit_project="proj1")
        assert manager.current_project == "proj1"

        # Second call uses sticky project
        name, _path, _prompt = manager.resolve_project("another task")
        assert name == "proj1"

    def test_switch_project(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test switching projects."""
        from agent_cli.claude_api import ProjectManager  # noqa: PLC0415

        manager = ProjectManager()
        manager.configure({"proj1": "/path/1", "proj2": "/path/2"}, default="proj1")

        path = manager.switch_project("proj2")
        assert path == "/path/2"
        assert manager.current_project == "proj2"


class TestLogStore:
    """Tests for the LogStore class."""

    def test_add_and_get_log(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test adding and retrieving a log entry."""
        from datetime import UTC, datetime  # noqa: PLC0415

        from agent_cli.claude_api import LogEntry, LogStore  # noqa: PLC0415

        store = LogStore()
        entry = LogEntry(
            log_id="test123",
            project="myproject",
            prompt="fix bug",
            summary="Fixed the bug",
            files_changed=["file.py"],
            tool_calls=[],
            full_response="I fixed it",
            timestamp=datetime.now(UTC),
            success=True,
        )
        store.add(entry)

        retrieved = store.get("test123")
        assert retrieved is not None
        assert retrieved.log_id == "test123"
        assert retrieved.project == "myproject"

    def test_get_nonexistent_log(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test getting a log that doesn't exist."""
        from agent_cli.claude_api import LogStore  # noqa: PLC0415

        store = LogStore()
        assert store.get("nonexistent") is None

    def test_list_recent(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test listing recent log entries."""
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        from agent_cli.claude_api import LogEntry, LogStore  # noqa: PLC0415

        store = LogStore()
        now = datetime.now(UTC)

        for i in range(5):
            entry = LogEntry(
                log_id=f"log{i}",
                project="proj",
                prompt=f"prompt {i}",
                summary=f"summary {i}",
                files_changed=[],
                tool_calls=[],
                full_response="",
                timestamp=now + timedelta(minutes=i),
                success=True,
            )
            store.add(entry)

        recent = store.list_recent(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0].log_id == "log4"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_extract_file_changes(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test extracting file changes from tool calls."""
        from agent_cli.claude_api import _extract_file_changes  # noqa: PLC0415

        tool_calls = [
            {"name": "Edit", "input": {"file_path": "/path/to/file1.py"}},
            {"name": "Write", "input": {"file_path": "/path/to/file2.py"}},
            {"name": "Read", "input": {"file_path": "/path/to/file3.py"}},  # Not a change
            {"name": "Edit", "input": {"file_path": "/path/to/file1.py"}},  # Duplicate
        ]

        files = _extract_file_changes(tool_calls)
        assert files == ["/path/to/file1.py", "/path/to/file2.py"]

    def test_truncate_prompt(self, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test prompt truncation."""
        from agent_cli.claude_api import PROMPT_TRUNCATE_LENGTH, _truncate_prompt  # noqa: PLC0415

        short = "short prompt"
        assert _truncate_prompt(short) == short

        long = "x" * (PROMPT_TRUNCATE_LENGTH + 10)
        truncated = _truncate_prompt(long)
        assert truncated.endswith("...")
        assert len(truncated) == PROMPT_TRUNCATE_LENGTH + 3


class TestNewEndpoints:
    """Tests for new endpoints."""

    def test_projects_endpoint(self, client: TestClient, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test the /projects endpoint."""
        response = client.get("/projects")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "default" in data
        assert "current" in data

    def test_logs_endpoint_empty(self, client: TestClient, mock_claude_sdk: Any) -> None:  # noqa: ARG002
        """Test the /logs endpoint when empty."""
        response = client.get("/logs")
        assert response.status_code == 200
        assert "No logs yet" in response.text
