"""Tests for the RAG proxy passthrough functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from agent_cli.rag.api import create_app

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture
def mock_rag_dependencies(mocker: MockerFixture) -> None:
    """Mock the RAG dependencies to avoid side effects."""
    mocker.patch("agent_cli.rag.api.init_collection")
    mocker.patch("agent_cli.rag.api.get_reranker_model")
    mocker.patch("agent_cli.rag.api.load_hashes_from_metadata", return_value=({}, {}))
    mocker.patch("agent_cli.rag.api.watch_docs")
    mocker.patch("agent_cli.rag.api.initial_index")
    # Also mock threading to prevent background threads
    mocker.patch("threading.Thread")


@pytest.fixture
def app(tmp_path: Path, mock_rag_dependencies: None) -> TestClient:  # noqa: ARG001
    """Create the FastAPI app with mocked dependencies."""
    fastapi_app = create_app(
        docs_folder=tmp_path / "docs",
        chroma_path=tmp_path / "chroma",
        openai_base_url="http://upstream.test/v1",
        chat_api_key="dummy-rag-key",
    )
    return TestClient(fastapi_app)


def test_rag_proxy_passthrough_models(app: TestClient, mocker: MockerFixture) -> None:
    """Test that /v1/models is forwarded to the upstream."""
    mock_send = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b'{"data": [{"id": "gpt-4"}]}'
    mock_response.headers = {"Content-Type": "application/json"}
    mock_send.return_value = mock_response

    mocker.patch("httpx.AsyncClient.send", side_effect=mock_send)

    response = app.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {"data": [{"id": "gpt-4"}]}

    assert mock_send.call_count == 1
    request_obj = mock_send.call_args[0][0]

    assert str(request_obj.url) == "http://upstream.test/v1/models"
    assert request_obj.method == "GET"
    # Ensure correct Auth header from RAG config
    assert request_obj.headers["Authorization"] == "Bearer dummy-rag-key"


def test_rag_proxy_passthrough_catchall(app: TestClient, mocker: MockerFixture) -> None:
    """Test that an arbitrary path is forwarded."""
    mock_send = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"OK"
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_send.return_value = mock_response

    mocker.patch("httpx.AsyncClient.send", side_effect=mock_send)

    response = app.post("/custom/endpoint", content=b"data")

    assert response.status_code == 200
    assert response.content == b"OK"

    assert mock_send.call_count == 1
    request_obj = mock_send.call_args[0][0]
    assert str(request_obj.url) == "http://upstream.test/v1/custom/endpoint"


def test_rag_proxy_passthrough_upstream_error(app: TestClient, mocker: MockerFixture) -> None:
    """Test handling of upstream errors."""
    mock_send = AsyncMock()
    mock_send.side_effect = Exception("Network error")

    mocker.patch("httpx.AsyncClient.send", side_effect=mock_send)

    response = app.get("/v1/models")

    assert response.status_code == 502
    assert response.content == b"Upstream Proxy Error"
