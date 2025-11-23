"""Integration tests for memory git versioning."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from agent_cli.memory import _ingest
from agent_cli.memory.client import MemoryClient
from agent_cli.memory.entities import Fact

if TYPE_CHECKING:
    from pathlib import Path


def _git_log(path: Path) -> list[str]:
    """Get git log as a list of strings."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline"],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip().splitlines()
    except subprocess.CalledProcessError:
        return []


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.asyncio
async def test_memory_client_git_versioning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that enabling git versioning initializes a repo and commits changes."""
    memory_path = tmp_path / "memory_db"

    # Mock LLM calls to avoid network dependency
    async def fake_extract(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["User likes testing"]

    async def fake_reconcile(
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[list[Fact], list[str], dict[str, str]]:
        # Always add the new fact
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id="default",
                content="User likes testing",
                source_id="source-id",
                created_at=datetime.now(UTC),
            ),
        ]
        return entries, [], {}

    async def fake_update_summary(*_args: Any, **_kwargs: Any) -> str:
        return "User likes testing."

    monkeypatch.setattr(_ingest, "extract_salient_facts", fake_extract)
    monkeypatch.setattr(_ingest, "reconcile_facts", fake_reconcile)
    monkeypatch.setattr(_ingest, "update_summary", fake_update_summary)

    # Patch Reranker to avoid loading ONNX model
    monkeypatch.setattr("agent_cli.memory.client.get_reranker_model", MagicMock())

    # Configure mock to return empty results so engine logic doesn't crash on pydantic validation
    mock_collection = MagicMock()
    mock_collection.get.return_value = {
        "documents": [],
        "metadatas": [],
        "ids": [],
    }
    mock_collection.query.return_value = {
        "documents": [[]],
        "metadatas": [[]],
        "ids": [[]],
        "distances": [[]],
    }

    monkeypatch.setattr(
        "agent_cli.memory.client.init_memory_collection",
        lambda *_args, **_kwargs: mock_collection,
    )
    # We also need to patch initial_index because it reads from disk and upserts to collection
    monkeypatch.setattr(
        "agent_cli.memory.client.initial_index",
        lambda *_args, **_kwargs: None,
    )
    # And watch_memory_store
    monkeypatch.setattr(
        "agent_cli.memory.client.watch_memory_store",
        lambda *_args, **_kwargs: None,
    )

    client = MemoryClient(
        memory_path=memory_path,
        openai_base_url="http://dummy",
        enable_git_versioning=True,
    )

    # 1. Check if git repo was initialized
    assert (memory_path / ".git").exists()
    assert (memory_path / ".gitignore").exists()
    assert (memory_path / "README.md").exists()

    # Check initial commit
    log = _git_log(memory_path)
    assert len(log) >= 1
    assert "Initial commit" in log[-1]

    # Verify gitignore content
    gitignore_content = (memory_path / ".gitignore").read_text()
    assert "chroma/" in gitignore_content
    assert "memory_index.json" in gitignore_content

    # 2. Add a memory and check for commit
    await client.add("I like testing")

    log_after = _git_log(memory_path)
    assert len(log_after) > len(log)
    latest_commit = log_after[0]
    assert "Add facts to conversation default" in latest_commit

    # Verify file exists
    facts = list((memory_path / "entries" / "default" / "facts").glob("*.md"))
    assert len(facts) == 1

    # 3. Verify that subsequent updates also commit (e.g. via chat/postprocess)
    async def fake_extract_2(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["User loves git"]

    async def fake_reconcile_2(
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[list[Fact], list[str], dict[str, str]]:
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id="default",
                content="User loves git",
                source_id="source-id",
                created_at=datetime.now(UTC),
            ),
        ]
        return entries, [], {}

    monkeypatch.setattr(_ingest, "extract_salient_facts", fake_extract_2)
    monkeypatch.setattr(_ingest, "reconcile_facts", fake_reconcile_2)

    await client.add("I love git")

    log_final = _git_log(memory_path)
    assert len(log_final) > len(log_after)
    assert "Add facts to conversation default" in log_final[0]
