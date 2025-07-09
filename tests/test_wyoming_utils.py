"""Tests for the Wyoming utilities."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.client import AsyncClient

from agent_cli.services._wyoming_utils import wyoming_client_context


@pytest.mark.asyncio
async def test_wyoming_client_context_success():
    """Test that the Wyoming client context manager connects successfully."""
    mock_client = AsyncMock(spec=AsyncClient)
    with patch(
        "agent_cli.services._wyoming_utils.AsyncClient.from_uri",
        return_value=MagicMock(
            __aenter__=AsyncMock(return_value=mock_client),
            __aexit__=AsyncMock(return_value=None),
        ),
    ):
        async with wyoming_client_context("localhost", 1234, "Test", logging.getLogger()) as client:
            assert client is mock_client


@pytest.mark.asyncio
async def test_wyoming_client_context_connection_refused(
    caplog: pytest.LogCaptureFixture,
):
    """Test that a ConnectionRefusedError is handled correctly."""
    with (
        patch(
            "agent_cli.services._wyoming_utils.AsyncClient.from_uri",
            side_effect=ConnectionRefusedError,
        ),
        pytest.raises(ConnectionRefusedError),
    ):
        async with wyoming_client_context("localhost", 1234, "Test", logging.getLogger()):
            pass  # This part should not be reached

    assert "Test connection refused" in caplog.text


@pytest.mark.asyncio
async def test_wyoming_client_context_generic_exception(
    caplog: pytest.LogCaptureFixture,
):
    """Test that a generic Exception is handled correctly."""
    with (
        patch(
            "agent_cli.services._wyoming_utils.AsyncClient.from_uri",
            side_effect=RuntimeError("Something went wrong"),
        ),
        pytest.raises(RuntimeError),
    ):
        async with wyoming_client_context("localhost", 1234, "Test", logging.getLogger()):
            pass  # This part should not be reached

    assert "An error occurred during test connection" in caplog.text
