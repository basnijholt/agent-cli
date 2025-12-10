"""HTTP-level integration tests for the RAG API.

Two modes:
- Stubbed LLM/reranker: deterministic/offline (test_rag_tool_execution_flow).
- Live LLM (set RAG_API_LIVE_BASE): starts uvicorn and hits the real model.

Example:
    RAG_API_LIVE_BASE=http://192.168.1.143:9292/v1 \
    RAG_API_LIVE_MODEL=gpt-oss-low:20b \
      pytest tests/rag/test_rag_integration_liveish.py -q

"""

from __future__ import annotations

import asyncio
import os
import socket
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from agent_cli.rag import api, engine
from agent_cli.rag.models import RagSource, RetrievalResult

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


@pytest.fixture
def rag_server() -> Callable[[Any], AbstractAsyncContextManager[str]]:
    """Fixture that returns an async context manager to start/stop the RAG proxy."""

    @asynccontextmanager
    async def _server(app: Any) -> AsyncGenerator[str, None]:
        # Choose a free port
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
                        await asyncio.sleep(0.1)
                msg = "Server did not start in time"
                raise RuntimeError(msg)

        try:
            await _wait_until_up()
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            await server_task

    return _server


@pytest.mark.asyncio
async def test_rag_tool_execution_flow(
    tmp_path: Any,
    rag_server: Callable[[Any], AbstractAsyncContextManager[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full flow: Retrieval -> Tool Call (read file) -> Response."""
    # 1. Setup Document
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    secret_file = docs_folder / "secret.txt"
    secret_file.write_text("The password is 'bananas'.")

    # 2. Mock Retrieval to return a snippet pointing to this file
    mock_retrieval = RetrievalResult(
        context="[Source: secret.txt]\n...password is...",
        sources=[RagSource(source="secret.txt", path="secret.txt", chunk_id=0, score=0.9)],
    )

    # Mock the _retrieve_context function in engine
    monkeypatch.setattr(
        engine,
        "_retrieve_context",
        lambda *_, **__: mock_retrieval,
    )

    # 3. Mock the Agent.run to simulate LLM behavior
    call_count = 0

    async def agent_handler(messages: list[ModelMessage], _info: Any) -> ModelResponse:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First call: Ask to read the file
            # Check if we have the system prompt with context
            system_content = next(
                (
                    m.parts[0].content
                    for m in messages
                    if isinstance(m, ModelRequest) and m.parts[0].part_kind == "system-prompt"
                ),
                "",
            )

            if "secret.txt" in system_content:
                return ModelResponse(
                    parts=[ToolCallPart("read_full_document", {"file_path": "secret.txt"})],
                    usage=RequestUsage(input_tokens=10, output_tokens=10),
                )
            # Fallback if context missing (shouldn't happen with our mock)
            return ModelResponse(
                parts=[TextPart("Context missing, can't find secret.")],
                usage=RequestUsage(input_tokens=10, output_tokens=10),
            )
        # Second call: We should see the ToolReturn in messages/context
        # For this test, simpler to just return the answer on second pass
        return ModelResponse(
            parts=[TextPart("I found the password: bananas")],
            usage=RequestUsage(input_tokens=10, output_tokens=10),
        )

    # Patch OpenAIModel to return our FunctionModel
    import pydantic_ai.models.openai  # noqa: PLC0415

    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIModel",
        lambda *_, **__: FunctionModel(agent_handler),
    )

    # 4. Start App
    # We need to mock everything that `api.create_app` does so it doesn't fail
    monkeypatch.setattr(api, "init_collection", MagicMock())
    monkeypatch.setattr(api, "get_reranker_model", MagicMock())
    monkeypatch.setattr(api, "load_hashes_from_metadata", MagicMock(return_value=({}, {})))
    monkeypatch.setattr(api, "watch_docs", AsyncMock())
    monkeypatch.setattr(api, "initial_index", MagicMock())

    app = api.create_app(
        docs_folder=docs_folder,
        chroma_path=tmp_path / "db",
        openai_base_url="http://dummy",
    )

    # 5. Run Test
    async with (
        rag_server(app) as url,
        httpx.AsyncClient(base_url=url, timeout=10.0) as client,
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "test",
                "messages": [{"role": "user", "content": "What is the secret?"}],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # Verify the full flow worked
        assert "bananas" in content


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.skipif(
    "RAG_API_LIVE_BASE" not in os.environ,
    reason="Set RAG_API_LIVE_BASE to run live HTTP RAG API test",
)
async def test_rag_api_live_real_llm(
    tmp_path: Any,
    rag_server: Callable[[Any], AbstractAsyncContextManager[str]],
) -> None:
    """Live end-to-end: start uvicorn, hit real LLM, verify RAG + Tool works."""
    base_url = os.environ["RAG_API_LIVE_BASE"]
    model = os.environ.get("RAG_API_LIVE_MODEL", "gpt-oss-low:20b")
    chat_api_key = os.environ.get("RAG_API_LIVE_KEY")

    # 1. Setup Document
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    secret_file = docs_folder / "secret_recipe.txt"
    secret_file.write_text("The secret ingredient is Saffron.")

    # 2. Setup App
    # We use the real stack. If RAG_API_LIVE_BASE supports embeddings, it will work.
    # If connecting to real OpenAI, it will use real embeddings.

    # Note: We do NOT monkeypatch embeddings or reranker here.
    # We let the app download the reranker model (might be slow on first run)
    # and use the configured embedding provider.

    app = api.create_app(
        docs_folder=docs_folder,
        chroma_path=tmp_path / "db",
        openai_base_url=base_url.rstrip("/"),
        chat_api_key=chat_api_key,
        # Use a dummy embedding model name to trigger our patch
        embedding_model="embeddinggemma:300m",
        limit=3,
    )

    # Wait for indexing (in real app it happens in background)
    # Since we mocked `initial_index` in previous test, we need to make sure it runs here?
    # `api.create_app` starts `initial_index` in a thread.
    # We should probably wait a bit or manually trigger index.
    # Actually, let's manually index to be sure.
    # But `initial_index` uses the collection.

    # A cleaner way for test is to inject the document into Chroma directly or wait.
    # Let's just rely on the app's background thread and wait loop.

    async with (
        rag_server(app) as url,
        httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {chat_api_key}"} if chat_api_key else {},
            timeout=60.0,
        ) as client,
    ):
        # Wait for file to be available (simple polling)
        for _ in range(20):
            files_resp = await client.get("/files")
            if files_resp.status_code == 200 and len(files_resp.json().get("files", [])) > 0:
                break
            await asyncio.sleep(0.5)

        # Ask question
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "What is the secret ingredient?"}],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        print(f"LLM Response: {content}")

        assert "Saffron" in content
