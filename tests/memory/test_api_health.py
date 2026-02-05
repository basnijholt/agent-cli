"""Smoke tests for memory API health and lifecycle."""

from __future__ import annotations

import sys
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.memory import api as memory_api


class _FakeCollection:
    pass


@pytest.mark.skipif(sys.platform == "win32", reason="Flaky on Windows: git subprocess hangs")
def test_memory_health_and_startup_shutdown(tmp_path: Any) -> None:
    started: list[str] = []

    async def _noop_watch(*_args: Any, **_kwargs: Any) -> None:
        started.append("watch")

    with ExitStack() as stack:
        stack.enter_context(
            patch("agent_cli.memory.client.watch_memory_store", side_effect=_noop_watch),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.init_memory_collection", return_value=_FakeCollection()),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.get_reranker_model", return_value=None),
        )

        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            embedding_model=DEFAULT_OPENAI_EMBEDDING_MODEL,
            enable_summarization=False,
        )
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert body["memory_store"] == str(tmp_path.resolve())

    # startup/shutdown should have triggered watch task creation
    assert started
