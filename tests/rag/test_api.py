"""Tests for RAG API."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.rag import api


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    with (
        patch("agent_cli.rag.api.init_collection"),
        patch("agent_cli.rag.api.get_reranker_model"),
        patch("agent_cli.rag.api.load_hashes_from_metadata", return_value={}),
        patch("pathlib.Path.mkdir"),
        patch("agent_cli.rag.api.watch_docs"),
        patch("asyncio.create_task"),
        patch("threading.Thread"),
    ):
        app = api.create_app(
            docs_folder=MagicMock(),
            chroma_path=MagicMock(),
            openai_base_url="http://mock-llama",
        )
        return TestClient(app)


def test_health(client: TestClient) -> None:
    """Test health endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_files(client: TestClient) -> None:
    """Test listing files."""
    with patch("agent_cli.rag.api.get_all_metadata") as mock_get:
        mock_get.return_value = [
            {"file_path": "f1.txt", "source": "f1", "file_type": ".txt", "indexed_at": "now"},
        ]

        resp = client.get("/files")
        assert resp.status_code == 200
        assert len(resp.json()["files"]) == 1
        assert resp.json()["files"][0]["path"] == "f1.txt"


def test_reindex(client: TestClient) -> None:
    """Test reindex endpoint."""
    with patch("threading.Thread") as mock_thread:
        resp = client.post("/reindex")
        assert resp.status_code == 200
        mock_thread.return_value.start.assert_called()


@pytest.mark.asyncio
async def test_chat_completion_extra_fields(client: TestClient) -> None:
    """Test that extra fields (like response_format) are accepted."""
    payload = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "response_format": {"type": "json_object"},
        "rag_top_k": 2,
    }

    with patch("agent_cli.rag.api.process_chat_request") as mock_process:
        mock_process.return_value = {"choices": []}

        resp = client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200

        # Verify that the request object passed to process_chat_request has the extra field
        call_args = mock_process.call_args
        assert call_args is not None
        chat_request = call_args[0][0]  # First arg is the ChatRequest object

        # Pydantic V2 stores extra fields in __pydantic_extra__ or directly accessible if allowed
        # We can check model_dump()
        dumped = chat_request.model_dump()
        assert "response_format" in dumped
        assert dumped["response_format"] == {"type": "json_object"}
