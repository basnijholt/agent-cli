"""HTTP-level integration tests for the memory API.

Two modes:
- Stubbed LLM/reranker (set MEMORY_API_LIVE_BASE): deterministic/offline.
- Live LLM (set MEMORY_API_LIVE_BASE): starts uvicorn and
  hits the real model. Example:
    MEMORY_API_LIVE_BASE=http://192.168.1.143:9292/v1 \
    MEMORY_API_LIVE_MODEL=gpt-oss-low:20b \
      pytest tests/memory/test_api_integration_liveish.py -q

  Note: Tests assume 'embeddinggemma:300m' is available on the server.
"""

from __future__ import annotations

import asyncio
import os
import socket
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
import pytest
import uvicorn
from chromadb.utils import embedding_functions

import agent_cli.memory._tasks as memory_tasks
import agent_cli.memory.api as memory_api
from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.memory import _ingest, engine
from agent_cli.memory.entities import Fact

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from fastapi import FastAPI

    from agent_cli.memory.models import ChatRequest


@pytest.fixture
def memory_proxy() -> Callable[[FastAPI], AbstractAsyncContextManager[str]]:
    """Fixture that returns an async context manager to start/stop the memory proxy."""

    @asynccontextmanager
    async def _server(app: FastAPI) -> AsyncGenerator[str, None]:
        # Choose a free port and start uvicorn in-process
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _host, port = s.getsockname()

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        async def _wait_until_up() -> None:
            health_url = f"http://127.0.0.1:{port}/health"
            async with httpx.AsyncClient() as client:
                for _ in range(60):
                    try:
                        resp = await client.get(health_url, timeout=0.5)
                        if resp.status_code == 200:
                            return
                    except Exception:
                        await asyncio.sleep(0.2)
                msg = "Server did not start in time"
                raise RuntimeError(msg)

        try:
            await _wait_until_up()
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            await server_task

    return _server


def _make_request_json(text: str) -> dict[str, Any]:
    return {
        "model": "demo-model",
        "messages": [
            {"role": "user", "content": text},
        ],
    }


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.skipif(
    "MEMORY_API_LIVE_BASE" not in os.environ,
    reason="Set MEMORY_API_LIVE_BASE to run HTTP memory API test against that base URL",
)
async def test_memory_api_updates_latest_fact(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    memory_proxy: Callable[[FastAPI], AbstractAsyncContextManager[str]],
) -> None:
    """End-to-end through the HTTP API with stubbed LLMs; latest fact should replace previous."""
    base_url = os.environ["MEMORY_API_LIVE_BASE"]

    # Use real ChromaDB but with local embeddings (DefaultEmbeddingFunction)
    # so we don't need a running embedding server or OpenAI key.
    real_ef = embedding_functions.DefaultEmbeddingFunction()
    monkeypatch.setattr(
        "agent_cli.core.chroma.embedding_functions.OpenAIEmbeddingFunction",
        lambda **_kwargs: real_ef,
    )

    # We remove the patch for init_memory_collection so it uses the real one.
    # We remove the patch for get_reranker_model so it uses the real one.

    async def _noop_watch(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("agent_cli.memory.client.watch_memory_store", _noop_watch)

    async def fake_forward_request(_request: ChatRequest, *_args: Any, **_kwargs: Any) -> Any:
        return {"choices": [{"message": {"content": "ok"}}]}

    async def fake_extract_salient_facts(user_message: str | None, **_kwargs: Any) -> list[str]:
        """Return a fact only when the user states a fact (contains 'my wife is')."""
        transcript = user_message or ""
        return [transcript] if "my wife is" in transcript else []

    async def fake_reconcile(
        _collection: Any,
        _conversation_id: str,
        new_facts: list[str],
        **_kwargs: Any,
    ) -> tuple[list[Fact], list[str], dict[str, str]]:
        """Latest wins: delete all existing, add new facts."""
        # Use real Chroma collection API
        results = _collection.get(where={"conversation_id": _conversation_id})
        existing_ids = results["ids"] if results else []
        if new_facts:
            entries = []
            replacement_map = {}
            for i, fact in enumerate(new_facts):
                new_id = str(uuid4())
                entries.append(
                    Fact(
                        id=new_id,
                        conversation_id=_conversation_id,
                        content=fact,
                        source_id="source-id",
                        created_at=datetime.now(UTC),
                    ),
                )
                if i < len(existing_ids):
                    replacement_map[existing_ids[i]] = new_id
            return entries, existing_ids, replacement_map
        return [], [], {}

    async def fake_update_summary(**_kwargs: Any) -> str | None:
        return "summary"

    monkeypatch.setattr(engine, "forward_chat_request", fake_forward_request)
    monkeypatch.setattr(_ingest, "extract_salient_facts", fake_extract_salient_facts)
    monkeypatch.setattr(_ingest, "reconcile_facts", fake_reconcile)
    monkeypatch.setattr(_ingest, "update_summary", fake_update_summary)

    app = memory_api.create_app(
        memory_path=tmp_path / "memory_db",
        openai_base_url=base_url,
        embedding_model=DEFAULT_OPENAI_EMBEDDING_MODEL,  # Will be intercepted by patch
        embedding_api_key=None,
        chat_api_key=None,
        enable_summarization=True,
    )

    async with (
        memory_proxy(app) as server_url,
        httpx.AsyncClient(base_url=server_url) as client,
    ):
        resp1 = await client.post(
            "/v1/chat/completions",
            json=_make_request_json("my wife is Jane"),
        )
        assert resp1.status_code == 200
        await memory_tasks.wait_for_background_tasks()

        # First fact should be persisted.
        facts_dir = tmp_path / "memory_db" / "entries" / "default" / "facts"
        fact_files_after_jane = sorted(facts_dir.glob("*.md"))
        assert len(fact_files_after_jane) == 1
        fact_jane = fact_files_after_jane[0].read_text()
        assert "Jane" in fact_jane

        # Ask a neutral question; should not create new facts.
        resp_question = await client.post(
            "/v1/chat/completions",
            json=_make_request_json("who is my wife"),
        )
        assert resp_question.status_code == 200
        await memory_tasks.wait_for_background_tasks()
        fact_files_after_question = sorted(facts_dir.glob("*.md"))
        assert fact_files_after_question == fact_files_after_jane

        resp2 = await client.post(
            "/v1/chat/completions",
            json=_make_request_json("my wife is Anne"),
        )
        assert resp2.status_code == 200
        await memory_tasks.wait_for_background_tasks()

        # Latest fact should replace the old one and tombstone the previous.
        fact_files_after_anne = sorted(facts_dir.glob("*.md"))
        assert len(fact_files_after_anne) == 1
        fact_anne = fact_files_after_anne[0].read_text()
        assert "Anne" in fact_anne
        assert "Jane" not in fact_anne

        # Tombstone should be in entries/deleted/default/facts
        deleted_dir = tmp_path / "memory_db" / "entries" / "deleted" / "default" / "facts"
        deleted_files = sorted(deleted_dir.glob("*.md"))
        assert deleted_files, "Expected tombstoned fact for Jane"

        deleted_content = "\n".join(f.read_text() for f in deleted_files)
        assert "Jane" in deleted_content

        # Ask again; facts should remain as Anne.
        resp_question2 = await client.post(
            "/v1/chat/completions",
            json=_make_request_json("who is my wife"),
        )
        assert resp_question2.status_code == 200
        await memory_tasks.wait_for_background_tasks()
        final_fact_files = sorted(facts_dir.glob("*.md"))
        assert final_fact_files == fact_files_after_anne


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(
    "MEMORY_API_LIVE_BASE" not in os.environ,
    reason="Set MEMORY_API_LIVE_BASE to run live HTTP memory API test",
)
async def test_memory_api_live_real_llm(  # noqa: PLR0915
    tmp_path: Path,
    memory_proxy: Callable[[FastAPI], AbstractAsyncContextManager[str]],
) -> None:
    """Live end-to-end: start uvicorn, hit real LLM, ensure Anne overwrites Jane."""
    base_url = os.environ["MEMORY_API_LIVE_BASE"]
    model = os.environ.get("MEMORY_API_LIVE_MODEL", "gpt-oss-low:20b")
    chat_api_key = os.environ.get("MEMORY_API_LIVE_KEY")

    app = memory_api.create_app(
        memory_path=tmp_path / "memory_db",
        openai_base_url=base_url.rstrip("/"),
        embedding_model="embeddinggemma:300m",
        embedding_api_key=chat_api_key,
        chat_api_key=chat_api_key,
        enable_summarization=True,
    )

    def _make_body(text: str) -> dict[str, Any]:
        return {"model": model, "messages": [{"role": "user", "content": text}]}

    facts_dir = tmp_path / "memory_db" / "entries" / "default" / "facts"
    deleted_dir = tmp_path / "memory_db" / "entries" / "default" / "deleted" / "facts"

    async def _wait_for_fact_contains(substr: str, timeout_s: float = 60.0) -> None:
        end = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < end:
            files = list(facts_dir.glob("*.md"))
            for path in files:
                content = path.read_text()
                if substr.lower() in content.lower():
                    return
            await asyncio.sleep(0.5)
        msg = f"Did not find fact containing {substr!r}"
        raise AssertionError(msg)

    async with (
        memory_proxy(app) as server_url,
        httpx.AsyncClient(
            base_url=server_url,
            headers={"Authorization": f"Bearer {chat_api_key}"} if chat_api_key else {},
            timeout=120.0,
        ) as client,
    ):
        resp1 = await client.post("/v1/chat/completions", json=_make_body("my wife is Jane"))
        assert resp1.status_code == 200
        await memory_tasks.wait_for_background_tasks()
        await _wait_for_fact_contains("jane")
        facts_after_jane = sorted(facts_dir.glob("*.md"))
        assert facts_after_jane, "Expected Jane fact"

        resp_q = await client.post("/v1/chat/completions", json=_make_body("who is my wife"))
        assert resp_q.status_code == 200
        await memory_tasks.wait_for_background_tasks()
        facts_after_q = sorted(facts_dir.glob("*.md"))
        assert len(facts_after_q) == len(facts_after_jane)

        resp2 = await client.post("/v1/chat/completions", json=_make_body("my wife is Anne"))
        assert resp2.status_code == 200
        await memory_tasks.wait_for_background_tasks()

        try:
            await _wait_for_fact_contains("anne")
        except AssertionError as exc:  # pragma: no cover - depends on live model behavior
            pytest.xfail(str(exc))
        facts_after_anne = sorted(facts_dir.glob("*.md"))
        assert facts_after_anne, "Expected Anne fact"

        # Ensure Anne present and Jane removed from active facts.
        anne_seen = any("anne" in p.read_text().lower() for p in facts_after_anne)
        jane_in_active = any("jane" in p.read_text().lower() for p in facts_after_anne)
        assert anne_seen
        assert not jane_in_active

        # Tombstone for Jane should exist.
        tombstones = sorted(deleted_dir.glob("*.md"))
        assert tombstones, "Expected tombstoned fact for Jane"
        deleted_content = "\n".join(p.read_text() for p in tombstones)
        assert "jane" in deleted_content.lower()

        resp_q2 = await client.post("/v1/chat/completions", json=_make_body("who is my wife"))
        assert resp_q2.status_code == 200
        await memory_tasks.wait_for_background_tasks()
        final_facts = sorted(facts_dir.glob("*.md"))
        jane_still = any(p.exists() and "jane" in p.read_text().lower() for p in final_facts)
        assert not jane_still
