"""Tests for the transcribe daemon agent."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003

import pytest


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
    try:
        from agent_cli.agents.transcribe_daemon import _log_segment  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

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
    try:
        from agent_cli.agents.transcribe_daemon import _log_segment  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

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
    try:
        from agent_cli.agents.transcribe_daemon import (  # noqa: PLC0415
            _generate_audio_path,
        )
    except ImportError:
        pytest.skip("silero-vad not installed")

    timestamp = datetime(2025, 1, 15, 10, 30, 45, 123000, tzinfo=UTC)
    path = _generate_audio_path(temp_audio_dir, timestamp)

    assert path.suffix == ".mp3"
    assert "2025/01/15" in str(path)
    assert "103045" in path.name  # HHMMSS


def test_get_audio_dir() -> None:
    """Test default audio directory path."""
    try:
        from agent_cli.agents.transcribe_daemon import _get_audio_dir  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

    audio_dir = _get_audio_dir()
    assert audio_dir.name == "audio"
    assert ".config" in str(audio_dir)
    assert "agent-cli" in str(audio_dir)


def test_get_log_file() -> None:
    """Test default log file path."""
    try:
        from agent_cli.agents.transcribe_daemon import _get_log_file  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

    log_file = _get_log_file()
    assert log_file.name == "transcriptions.jsonl"
    assert ".config" in str(log_file)
    assert "agent-cli" in str(log_file)


def test_transcribe_daemon_command_exists() -> None:
    """Test that the transcribe-daemon command is registered."""
    try:
        from agent_cli.agents.transcribe_daemon import (  # noqa: PLC0415
            transcribe_daemon,
        )
    except ImportError:
        pytest.skip("silero-vad not installed")

    assert callable(transcribe_daemon)


def test_process_name_constant() -> None:
    """Test the process name used for the daemon."""
    try:
        # Check that the command function exists and would use correct process name
        from agent_cli.agents import transcribe_daemon as td_module  # noqa: PLC0415

        # The process name is defined inside the function, so we just verify
        # the module loads correctly
        assert hasattr(td_module, "transcribe_daemon")
    except ImportError:
        pytest.skip("silero-vad not installed")
