"""Tests for the memory proxy passthrough functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from agent_cli.memory.api import create_app

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture
def mock_memory_client(mocker: MockerFixture) -> Mock:
    """Mock the MemoryClient to avoid side effects."""
    mock_client_cls = mocker.patch("agent_cli.memory.api.MemoryClient")
    mock_client = mock_client_cls.return_value
    mock_client.memory_path = "dummy_path"
    mock_client.openai_base_url = "http://upstream.test/v1"
    mock_client.chat_api_key = "dummy-key"
    mock_client.default_top_k = 5
    return mock_client


@pytest.fixture
def app(tmp_path: Path, mock_memory_client: Mock) -> TestClient:  # noqa: ARG001
    """Create the FastAPI app with mocked client."""
    fastapi_app = create_app(
        memory_path=tmp_path,
        openai_base_url="http://upstream.test/v1",
    )
    return TestClient(fastapi_app)


def test_proxy_passthrough_models(app: TestClient, mocker: MockerFixture) -> None:
    """Test that /v1/models is forwarded to the upstream."""
    # Mock httpx.AsyncClient.send
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

    # Verify the request was constructed correctly
    assert mock_send.call_count == 1
    call_args = mock_send.call_args
    request_obj = call_args[0][0]

    # Check that URL was constructed correctly (v1 should not be duplicated if base has it)
    # base="http://upstream.test/v1", path="v1/models" -> "http://upstream.test/v1/models"
    assert str(request_obj.url) == "http://upstream.test/v1/models"
    assert request_obj.method == "GET"


def test_proxy_passthrough_catchall_other_path(app: TestClient, mocker: MockerFixture) -> None:
    """Test that an arbitrary path is forwarded."""
    mock_send = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"OK"
    mock_response.headers = {"Content-Type": "text/plain"}
    mock_send.return_value = mock_response

    mocker.patch("httpx.AsyncClient.send", side_effect=mock_send)

    response = app.post("/other/path?foo=bar", content=b"payload")

    assert response.status_code == 200
    assert response.content == b"OK"

    # Verify construction
    assert mock_send.call_count == 1
    request_obj = mock_send.call_args[0][0]
    assert str(request_obj.url) == "http://upstream.test/v1/other/path?foo=bar"
    assert request_obj.method == "POST"
    # Note: TestClient sends body, but httpx.build_request might consume it differently
    # depending on how we mock. We just verify the call happened.


def test_proxy_passthrough_upstream_error(app: TestClient, mocker: MockerFixture) -> None:
    """Test handling of upstream errors."""
    mock_send = AsyncMock()
    mock_send.side_effect = Exception("Connection refused")

    mocker.patch("httpx.AsyncClient.send", side_effect=mock_send)

    response = app.get("/v1/models")

    assert response.status_code == 502
    assert response.content == b"Upstream Proxy Error"
