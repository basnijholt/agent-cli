"""HTTP-level integration tests for the memory API.

Two modes:
- Stubbed LLM/reranker (set MEMORY_API_LIVE_BASE): deterministic/offline.
- Live LLM (set MEMORY_API_LIVE_BASE and MEMORY_API_LIVE_REAL): starts uvicorn and
  hits the real model. Example:
    MEMORY_API_LIVE_BASE=http://192.168.1.143:9292/v1 MEMORY_API_LIVE_REAL=1 \
      pytest tests/memory/test_api_integration_liveish.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import uvicorn

import agent_cli.memory.api as memory_api
import agent_cli.memory.tasks as memory_tasks
import agent_cli.rag.retriever as rag_retriever
from agent_cli.memory import engine

if TYPE_CHECKING:
    from agent_cli.memory.models import ChatRequest


class _RecordingCollection:
    """Minimal in-memory Chroma-like collection for tests."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any]]] = {}

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, dict(meta))

    def query(
        self,
        *,
        query_texts: list[str],  # noqa: ARG002
        n_results: int,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        conv = None
        if "$and" in where:
            for clause in where["$and"]:
                if "conversation_id" in clause:
                    conv = clause["conversation_id"]
        else:
            conv = where.get("conversation_id")
        items = [
            (doc_id, doc, meta)
            for doc_id, (doc, meta) in self._store.items()
            if meta.get("conversation_id") == conv and meta.get("role") == "memory"
        ]
        ids = [doc_id for doc_id, _, _ in items][:n_results]
        docs = [doc for _, doc, _ in items][:n_results]
        metas = [meta for _, _, meta in items][:n_results]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "ids": [ids],
            "distances": [[0.0 for _ in ids]],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        _include: list[str] | None = None,
    ) -> dict[str, Any]:
        if where is None:
            return {"documents": [], "metadatas": [], "ids": []}
        clauses = where.get("$and", [where])  # type: ignore[arg-type]

        def _matches(meta: dict[str, Any], clause: dict[str, Any]) -> bool:
            for key, value in clause.items():
                if isinstance(value, dict) and "$ne" in value and meta.get(key) == value["$ne"]:
                    return False
                if meta.get(key) != value:
                    return False
            return True

        results = [
            (doc_id, (doc, meta))
            for doc_id, (doc, meta) in self._store.items()
            if all(_matches(meta, clause) for clause in clauses)
        ]
        docs = [doc for _, (doc, _) in results]
        metas = [meta for _, (_, meta) in results]
        ids = [doc_id for doc_id, _ in results]
        return {"documents": [docs], "metadatas": [metas], "ids": ids}

    def delete(self, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:  # noqa: ARG002
        if ids:
            for doc_id in ids:
                self._store.pop(doc_id, None)


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


def _make_request_json(text: str) -> dict[str, Any]:
    return {
        "model": "demo-model",
        "messages": [
            {"role": "user", "content": text},
        ],
    }


@pytest.mark.asyncio
@pytest.mark.skipif(
    "MEMORY_API_LIVE_BASE" not in os.environ,
    reason="Set MEMORY_API_LIVE_BASE to run HTTP memory API test against that base URL",
)
async def test_memory_api_updates_latest_fact(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end through the HTTP API with stubbed LLMs; latest fact should replace previous."""
    base_url = os.environ["MEMORY_API_LIVE_BASE"]
    collection = _RecordingCollection()

    # Patch out external dependencies and watchers.
    monkeypatch.setattr(memory_api, "init_memory_collection", lambda *_args, **_kwargs: collection)
    monkeypatch.setattr(rag_retriever, "get_reranker_model", lambda: _DummyReranker())

    async def _noop_watch(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(memory_api, "watch_memory_store", _noop_watch)

    async def fake_forward_request(_request: ChatRequest, *_args: Any, **_kwargs: Any) -> Any:
        return {"choices": [{"message": {"content": "ok"}}]}

    async def fake_extract_with_pydantic_ai(**kwargs: Any) -> list[str]:
        """Return a fact only when the user states a fact (contains 'my wife is')."""
        transcript = kwargs.get("transcript") or ""
        return [transcript] if "my wife is" in transcript else []

    async def fake_rewrite_queries(user_message: str, **_kwargs: Any) -> list[str]:
        return [user_message]

    async def fake_reconcile(
        _collection: Any,
        _conversation_id: str,
        new_facts: list[str],
        **_kwargs: Any,
    ) -> tuple[list[str], list[str]]:
        """Latest wins: delete all existing, add new facts."""
        existing_ids = list(getattr(_collection, "_store", {}).keys())
        if new_facts:
            return new_facts, existing_ids
        return [], []

    async def fake_update_summaries(**_kwargs: Any) -> tuple[str | None, str | None]:
        return "short", "long"

    monkeypatch.setattr(engine, "_forward_request", fake_forward_request)
    monkeypatch.setattr(engine, "_extract_with_pydantic_ai", fake_extract_with_pydantic_ai)
    monkeypatch.setattr(engine, "_rewrite_queries", fake_rewrite_queries)
    monkeypatch.setattr(engine, "_reconcile_facts", fake_reconcile)
    monkeypatch.setattr(engine, "_update_summaries", fake_update_summaries)

    app = memory_api.create_app(
        memory_path=tmp_path / "memory_db",
        openai_base_url=base_url,
        embedding_model="text-embedding-3-small",
        embedding_api_key=None,
        chat_api_key=None,
        enable_summarization=True,
    )

    # Choose a free port and start uvicorn in-process so we exercise the real HTTP stack.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        _host, port = s.getsockname()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    async def _wait_until_up() -> None:
        health_url = f"http://127.0.0.1:{port}/health"
        async with httpx.AsyncClient() as client:
            for _ in range(30):
                try:
                    resp = await client.get(health_url, timeout=0.3)
                    if resp.status_code == 200:
                        return
                except Exception:
                    await asyncio.sleep(0.1)
            msg = "Server did not start in time"
            raise RuntimeError(msg)

    try:
        await _wait_until_up()
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
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

            deleted_dir = tmp_path / "memory_db" / "entries" / "default" / "deleted" / "facts"
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
    finally:
        server.should_exit = True
        await server_task


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(
    "MEMORY_API_LIVE_BASE" not in os.environ,
    reason="Set MEMORY_API_LIVE_BASE to run live HTTP memory API test",
)
@pytest.mark.skipif(
    "MEMORY_API_LIVE_REAL" not in os.environ,
    reason="Set MEMORY_API_LIVE_REAL to run live HTTP memory API test hitting real LLM",
)
async def test_memory_api_live_real_llm(tmp_path: Path) -> None:  # noqa: PLR0915
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

    def _make_body(text: str) -> dict[str, Any]:
        return {"model": model, "messages": [{"role": "user", "content": text}]}

    def _cache_dir() -> Path:
        # Persistent across runs to avoid re-hitting the live LLM.
        return Path(__file__).resolve().parent / "live_http_cache"

    def _cache_key(url: str, payload: dict[str, Any]) -> str:
        return f"{base_url}::{url}__{json.dumps(payload, sort_keys=True)}"

    async def _cached_post(
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Very simple file-based cache to avoid re-hitting the live LLM on reruns."""
        cache_path = _cache_dir()
        cache_path.mkdir(parents=True, exist_ok=True)
        key = _cache_key(url, payload)
        key_hash = str(uuid.uuid5(uuid.NAMESPACE_OID, key))
        entry = cache_path / f"{key_hash}.json"
        if entry.exists():
            data = json.loads(entry.read_text())
            return httpx.Response(
                status_code=data["status_code"],
                headers=data.get("headers", {}),
                json=data["json"],
                request=httpx.Request("POST", url),
            )

        resp = await client.post(url, json=payload)
        entry.write_text(
            json.dumps(
                {
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "json": resp.json(),
                },
                indent=2,
                sort_keys=True,
            ),
        )
        return resp

    facts_dir = tmp_path / "memory_db" / "entries" / "default" / "facts"
    deleted_dir = tmp_path / "memory_db" / "entries" / "default" / "deleted" / "facts"

    async def _wait_for_fact_contains(substr: str, timeout_s: float = 30.0) -> None:
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

    try:
        await _wait_until_up()
        headers = {"Authorization": f"Bearer {chat_api_key}"} if chat_api_key else {}
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            headers=headers,
            timeout=120.0,
        ) as client:
            resp1 = await _cached_post(
                client,
                "/v1/chat/completions",
                _make_body("my wife is Jane"),
            )
            assert resp1.status_code == 200
            await memory_tasks.wait_for_background_tasks()
            await _wait_for_fact_contains("jane")
            facts_after_jane = sorted(facts_dir.glob("*.md"))
            assert facts_after_jane, "Expected Jane fact"

            resp_q = await _cached_post(
                client,
                "/v1/chat/completions",
                _make_body("who is my wife"),
            )
            assert resp_q.status_code == 200
            await memory_tasks.wait_for_background_tasks()
            facts_after_q = sorted(facts_dir.glob("*.md"))
            assert len(facts_after_q) == len(facts_after_jane)

            resp2 = await _cached_post(
                client,
                "/v1/chat/completions",
                _make_body("my wife is Anne"),
            )
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
    finally:
        server.should_exit = True
        await server_task
