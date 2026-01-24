"""Shared test fixtures and configuration."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import sys
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from agent_cli.core import deps


def _mock_check_extra_installed(extra: str) -> bool:  # noqa: ARG001
    """Always return True for tests - all extras assumed available."""
    return True


def pytest_configure() -> None:
    """Pre-configure mocks before test collection.

    This is needed because @patch("sounddevice.query_devices") decorators
    import sounddevice during test collection, which triggers Pa_Initialize()
    and hangs on Windows CI without audio hardware.

    Also mocks check_extra_installed to always return True so tests that
    exercise command logic don't fail on missing optional dependencies.
    """
    if "sounddevice" not in sys.modules:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = []
        mock_sd.InputStream = MagicMock()
        mock_sd.OutputStream = MagicMock()
        sys.modules["sounddevice"] = mock_sd

    # Mock check_extra_installed to always return True for tests
    # This allows tests to exercise command logic without needing all extras
    deps.check_extra_installed = _mock_check_extra_installed


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
def mock_audio_device_info() -> list[dict]:
    """Mock audio device info for testing."""
    return [
        {
            "index": 0,
            "name": "Mock Input Device",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "default_samplerate": 44100.0,
        },
        {
            "index": 1,
            "name": "Mock Output Device",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 44100.0,
        },
        {
            "index": 2,
            "name": "Mock Combined Device",
            "max_input_channels": 2,
            "max_output_channels": 2,
            "default_samplerate": 44100.0,
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
