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
