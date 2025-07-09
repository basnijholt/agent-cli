"""Shared test fixtures and configuration."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging

import pytest
from rich.console import Console


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Set default timeout for all tests."""
    for item in items:
        with contextlib.suppress(AttributeError):
            item.add_marker(pytest.mark.timeout(3))


@pytest.fixture
def mock_console() -> Console:
    """Provide a console that writes to a StringIO for testing."""
    return Console(file=io.StringIO(), width=80, force_terminal=True)


@pytest.fixture
def mock_logger() -> logging.Logger:
    """Provide a mock logger for testing."""
    logger = logging.getLogger("test")
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture
def stop_event() -> asyncio.Event:
    """Provide an asyncio event for stopping operations."""
    return asyncio.Event()


@pytest.fixture
def timeout_seconds() -> float:
    """Default timeout for async operations in tests."""
    return 5.0


@pytest.fixture
def mock_pyaudio_device_info() -> list[dict]:
    """Mock PyAudio device info for testing."""
    return [
        {
            "index": 0,
            "name": "Mock Input Device",
            "maxInputChannels": 2,
            "maxOutputChannels": 0,
            "defaultSampleRate": 44100.0,
        },
        {
            "index": 1,
            "name": "Mock Output Device",
            "maxInputChannels": 0,
            "maxOutputChannels": 2,
            "defaultSampleRate": 44100.0,
        },
        {
            "index": 2,
            "name": "Mock Combined Device",
            "maxInputChannels": 2,
            "maxOutputChannels": 2,
            "defaultSampleRate": 44100.0,
        },
    ]


@pytest.fixture
def llm_responses() -> dict[str, str]:
    """Predefined LLM responses for testing."""
    return {
        "correct": "This text has been corrected and improved.",
        "hello": "Hello! How can I help you today?",
        "question": "The meaning of life is 42, according to The Hitchhiker's Guide to the Galaxy.",
        "default": "I understand your request and here is my response.",
    }
