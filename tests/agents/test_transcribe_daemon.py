"""Tests for the transcribe daemon agent."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agent_cli.agents.transcribe_daemon import (
    _DEFAULT_AUDIO_DIR,
    _DEFAULT_LOG_FILE,
    _generate_audio_path,
    _log_segment,
    transcribe_daemon,
)


@pytest.fixture
def temp_log_file(tmp_path: Path) -> Path:
    """Create a temporary log file path."""
    return tmp_path / "transcriptions.jsonl"


@pytest.fixture
def temp_audio_dir(tmp_path: Path) -> Path:
    """Create a temporary audio directory."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    return audio_dir


def test_log_segment(temp_log_file: Path, tmp_path: Path) -> None:
    """Test logging a transcription segment."""
    audio_file = tmp_path / "test.mp3"
    timestamp = datetime.now(UTC)
    _log_segment(
        temp_log_file,
        timestamp=timestamp,
        role="test",
        raw_output="hello world",
        processed_output="Hello, world.",
        audio_file=audio_file,
        duration_seconds=2.5,
        model_info="test:model",
    )

    # Read and verify log entry
    assert temp_log_file.exists()
    with temp_log_file.open() as f:
        line = f.readline()
        entry = json.loads(line)

    assert entry["role"] == "test"
    assert entry["raw_output"] == "hello world"
    assert entry["processed_output"] == "Hello, world."
    assert entry["audio_file"] == str(audio_file)
    assert entry["duration_seconds"] == 2.5
    assert entry["model"] == "test:model"


def test_log_segment_creates_parent_dirs(tmp_path: Path) -> None:
    """Test that log_segment creates parent directories."""
    log_file = tmp_path / "nested" / "dir" / "log.jsonl"

    _log_segment(
        log_file,
        timestamp=datetime.now(UTC),
        role="test",
        raw_output="test",
        processed_output=None,
        audio_file=None,
        duration_seconds=1.0,
    )

    assert log_file.exists()


def test_generate_audio_path(temp_audio_dir: Path) -> None:
    """Test audio path generation with date-based structure."""
    timestamp = datetime(2025, 1, 15, 10, 30, 45, 123000, tzinfo=UTC)
    path = _generate_audio_path(temp_audio_dir, timestamp)

    assert path.suffix == ".mp3"
    assert path.parts[-4:-1] == ("2025", "01", "15")  # Date directories
    assert "103045" in path.name  # HHMMSS


def test_default_audio_dir() -> None:
    """Test default audio directory path."""
    assert _DEFAULT_AUDIO_DIR.name == "audio"
    assert ".config" in str(_DEFAULT_AUDIO_DIR)
    assert "agent-cli" in str(_DEFAULT_AUDIO_DIR)


def test_default_log_file() -> None:
    """Test default log file path."""
    assert _DEFAULT_LOG_FILE.name == "transcriptions.jsonl"
    assert ".config" in str(_DEFAULT_LOG_FILE)
    assert "agent-cli" in str(_DEFAULT_LOG_FILE)


def test_transcribe_daemon_command_exists() -> None:
    """Test that the transcribe-daemon command is registered."""
    assert callable(transcribe_daemon)
