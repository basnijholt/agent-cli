"""Tests for the transcribe daemon agent."""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents.transcribe_daemon import (
    _DEFAULT_AUDIO_DIR,
    _DEFAULT_LOG_FILE,
    _MIN_SEGMENT_DURATION_SECONDS,
    DaemonConfig,
    _generate_audio_path,
    _log_segment,
    _process_segment,
    transcribe_daemon,
)

if TYPE_CHECKING:
    from pathlib import Path


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


def test_min_segment_duration_constant() -> None:
    """Test that the minimum segment duration constant is defined."""
    assert _MIN_SEGMENT_DURATION_SECONDS == 0.3


@pytest.fixture
def mock_vad() -> MagicMock:
    """Create a mock VoiceActivityDetector."""
    vad = MagicMock()
    vad.get_segment_duration_seconds.return_value = 1.0  # 1 second segment
    return vad


@pytest.fixture
def daemon_config(tmp_path: Path, mock_vad: MagicMock) -> DaemonConfig:
    """Create a DaemonConfig for testing."""
    return DaemonConfig(
        role="test",
        vad=mock_vad,
        input_device_index=0,
        provider=config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        ),
        wyoming_asr=config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        ),
        openai_asr=config.OpenAIASR(
            asr_openai_model="whisper-1",
            openai_api_key=None,
            openai_base_url=None,
            asr_openai_prompt=None,
        ),
        gemini_asr=config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
            gemini_api_key=None,
        ),
        ollama=config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        ),
        openai_llm=config.OpenAILLM(
            llm_openai_model="gpt-4",
            openai_api_key=None,
            openai_base_url=None,
        ),
        gemini_llm=config.GeminiLLM(
            llm_gemini_model="gemini-2.0-flash",
            gemini_api_key=None,
        ),
        llm_enabled=False,
        save_audio=False,
        audio_dir=tmp_path / "audio",
        log_file=tmp_path / "transcriptions.jsonl",
        quiet=True,
        clipboard=False,
    )


def test_daemon_config_creation(daemon_config: DaemonConfig) -> None:
    """Test that DaemonConfig can be created with all required fields."""
    assert daemon_config.role == "test"
    assert daemon_config.llm_enabled is False
    assert daemon_config.save_audio is False
    assert daemon_config.quiet is True
    assert daemon_config.clipboard is False


@pytest.mark.asyncio
async def test_process_segment_skips_short_segments(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment skips segments shorter than minimum duration."""
    # Configure VAD to return short duration (vad is a MagicMock in tests)
    daemon_config.vad.get_segment_duration_seconds.return_value = 0.1  # type: ignore[attr-defined]

    timestamp = datetime.now(UTC)
    segment = b"\x00" * 1000

    # Should return early without processing
    with patch(
        "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
    ) as mock_transcriber:
        await _process_segment(daemon_config, segment, timestamp)
        # Transcriber should not be called for short segments
        mock_transcriber.assert_not_called()


@pytest.mark.asyncio
async def test_process_segment_transcribes_audio(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment transcribes audio and logs result."""
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000  # 1 second of audio

    mock_transcriber = AsyncMock(return_value="Hello world")

    with patch(
        "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
        return_value=mock_transcriber,
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # Verify transcription was called
    mock_transcriber.assert_called_once()

    # Verify log file was written
    assert daemon_config.log_file.exists()
    with daemon_config.log_file.open() as f:
        entry = json.loads(f.readline())
    assert entry["raw_output"] == "Hello world"
    assert entry["role"] == "test"


@pytest.mark.asyncio
async def test_process_segment_skips_empty_transcript(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment skips logging for empty transcripts."""
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="")  # Empty transcript

    with patch(
        "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
        return_value=mock_transcriber,
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # Log file should not exist (no log entry written)
    assert not daemon_config.log_file.exists()


@pytest.mark.asyncio
async def test_process_segment_with_llm_enabled(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment uses LLM when enabled."""
    daemon_config.llm_enabled = True
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="hello world")
    mock_llm_processor = AsyncMock(return_value="Hello, world.")

    with (
        patch(
            "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
            return_value=mock_transcriber,
        ),
        patch(
            "agent_cli.agents.transcribe_daemon.process_and_update_clipboard",
            mock_llm_processor,
        ),
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # LLM processor should be called
    mock_llm_processor.assert_called_once()

    # Log should contain both raw and processed output
    with daemon_config.log_file.open() as f:
        entry = json.loads(f.readline())
    assert entry["raw_output"] == "hello world"
    assert entry["processed_output"] == "Hello, world."
    assert "ollama" in entry["model"]


@pytest.mark.asyncio
async def test_process_segment_with_clipboard(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment copies to clipboard when enabled."""
    daemon_config.clipboard = True
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="Hello world")

    with (
        patch(
            "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
            return_value=mock_transcriber,
        ),
        patch("pyperclip.copy") as mock_copy,
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # Clipboard should be updated
    mock_copy.assert_called_once_with("Hello world")


@pytest.mark.asyncio
async def test_process_segment_saves_audio(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment saves audio as MP3 when enabled."""
    daemon_config.save_audio = True
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="Hello world")

    with (
        patch(
            "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
            return_value=mock_transcriber,
        ),
        patch(
            "agent_cli.agents.transcribe_daemon.save_audio_as_mp3",
        ) as mock_save_mp3,
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # MP3 save should be called
    mock_save_mp3.assert_called_once()
    call_args = mock_save_mp3.call_args
    assert call_args[0][0] == segment  # First arg is segment
    assert call_args[0][1].suffix == ".mp3"  # Second arg is path with .mp3 extension


@pytest.mark.asyncio
async def test_process_segment_handles_mp3_save_error(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment handles MP3 save errors gracefully."""
    daemon_config.save_audio = True
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="Hello world")

    with (
        patch(
            "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
            return_value=mock_transcriber,
        ),
        patch(
            "agent_cli.agents.transcribe_daemon.save_audio_as_mp3",
            side_effect=RuntimeError("FFmpeg not found"),
        ),
    ):
        # Should not raise, just log the error
        await _process_segment(daemon_config, segment, timestamp)

    # Transcription should still be logged
    assert daemon_config.log_file.exists()


@pytest.mark.asyncio
async def test_process_segment_with_openai_provider(
    daemon_config: DaemonConfig,
) -> None:
    """Test that _process_segment uses correct transcriber for OpenAI provider."""
    daemon_config.provider.asr_provider = "openai"
    timestamp = datetime.now(UTC)
    segment = b"\x00" * 32000

    mock_transcriber = AsyncMock(return_value="Hello world")

    with patch(
        "agent_cli.agents.transcribe_daemon.create_recorded_audio_transcriber",
        return_value=mock_transcriber,
    ):
        await _process_segment(daemon_config, segment, timestamp)

    # Verify transcriber was called with correct arguments for OpenAI
    mock_transcriber.assert_called_once()
    # OpenAI provider passes positional args
    call_args = mock_transcriber.call_args
    assert call_args[0][0] == segment

    # Log should contain openai model info
    with daemon_config.log_file.open() as f:
        entry = json.loads(f.readline())
    assert "openai" in entry["model"]


def test_log_segment_includes_hostname(temp_log_file: Path) -> None:
    """Test that log entries include hostname."""
    _log_segment(
        temp_log_file,
        timestamp=datetime.now(UTC),
        role="test",
        raw_output="test",
        processed_output=None,
        audio_file=None,
        duration_seconds=1.0,
    )

    with temp_log_file.open() as f:
        entry = json.loads(f.readline())

    assert entry["hostname"] == platform.node()


def test_log_segment_handles_unicode(temp_log_file: Path) -> None:
    """Test that log entries handle unicode characters correctly."""
    _log_segment(
        temp_log_file,
        timestamp=datetime.now(UTC),
        role="test",
        raw_output="Hello 世界 🌍",
        processed_output="Привет мир",
        audio_file=None,
        duration_seconds=1.0,
    )

    with temp_log_file.open(encoding="utf-8") as f:
        entry = json.loads(f.readline())

    assert entry["raw_output"] == "Hello 世界 🌍"
    assert entry["processed_output"] == "Привет мир"


def test_generate_audio_path_creates_directories(tmp_path: Path) -> None:
    """Test that audio path generation creates necessary directories."""
    audio_dir = tmp_path / "audio"
    # Directory doesn't exist yet
    assert not audio_dir.exists()

    timestamp = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
    path = _generate_audio_path(audio_dir, timestamp)

    # Directory should now exist
    assert path.parent.exists()
    assert path.parent.name == "15"  # Day
    assert path.parent.parent.name == "06"  # Month
    assert path.parent.parent.parent.name == "2025"  # Year


def test_generate_audio_path_includes_milliseconds(tmp_path: Path) -> None:
    """Test that audio path includes milliseconds for uniqueness."""
    audio_dir = tmp_path / "audio"
    timestamp = datetime(2025, 1, 15, 10, 30, 45, 567000, tzinfo=UTC)
    path = _generate_audio_path(audio_dir, timestamp)

    # Should include milliseconds in filename
    assert "567" in path.name
