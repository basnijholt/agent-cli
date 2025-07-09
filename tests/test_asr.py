"""Unit tests for the asr module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.asr import Transcript

from agent_cli.services.factory import get_asr_service
from agent_cli.services.local.asr import WyomingASRService
from agent_cli.services.openai.asr import OpenAIASRService


def test_get_asr_service():
    """Test that the correct ASR service is returned."""
    provider_cfg = MagicMock()
    provider_cfg.asr_provider = "openai"
    service = get_asr_service(provider_cfg, MagicMock(), MagicMock(), is_interactive=False)
    assert isinstance(service, OpenAIASRService)

    provider_cfg.asr_provider = "local"
    service = get_asr_service(provider_cfg, MagicMock(), MagicMock(), is_interactive=False)
    assert isinstance(service, WyomingASRService)


@pytest.mark.asyncio
@patch("agent_cli.services.local.asr.wyoming_client_context")
async def test_wyoming_asr_service_transcribe(mock_wyoming_client_context: MagicMock):
    """Test that the WyomingASRService transcribes audio."""
    mock_client = AsyncMock()
    mock_client.read_event.side_effect = [Transcript(text="hello world").event(), None]
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_client

    service = WyomingASRService(wyoming_asr_config=MagicMock(), is_interactive=False)
    result = await service.transcribe(b"test")
    assert result == "hello world"
    mock_wyoming_client_context.assert_called_once()


@pytest.mark.asyncio
@patch(
    "agent_cli.services.local.asr.wyoming_client_context",
    side_effect=ConnectionRefusedError,
)
async def test_wyoming_asr_service_transcribe_connection_error(
    mock_wyoming_client_context: MagicMock,
):
    """Test that the WyomingASRService handles ConnectionRefusedError."""
    service = WyomingASRService(wyoming_asr_config=MagicMock(), is_interactive=False)
    result = await service.transcribe(b"test")
    assert result == ""
    mock_wyoming_client_context.assert_called_once()


@pytest.mark.asyncio
async def test_openai_asr_service_transcribe():
    """Test that the OpenAIASRService transcribes audio."""
    service = OpenAIASRService(openai_asr_config=MagicMock(), is_interactive=False)
    result = await service.transcribe(b"test")
    assert result == "This is a test"


@pytest.mark.asyncio
async def test_openai_asr_service_transcribe_no_audio():
    """Test that the OpenAIASRService returns an empty string for no audio."""
    service = OpenAIASRService(openai_asr_config=MagicMock(), is_interactive=False)
    result = await service.transcribe(b"")
    assert result == ""
