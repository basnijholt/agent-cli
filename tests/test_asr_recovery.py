"""Tests for the ASR recovery features."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config, constants
from agent_cli.services import asr
from tests.mocks.audio import MockSoundDeviceStream


def create_test_wav_file(filepath: Path, duration_seconds: float = 1.0) -> None:
    """Create a test WAV file with silence."""
    sample_rate = constants.AUDIO_RATE
    channels = constants.AUDIO_CHANNELS
    sample_width = 2  # 16-bit

    num_samples = int(sample_rate * duration_seconds)
    audio_data = b"\x00\x00" * num_samples  # 16-bit silence

    with wave.open(str(filepath), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data)


def test_get_transcriptions_dir():
    """Test that the transcriptions directory is created correctly."""
    transcriptions_dir = asr._get_transcriptions_dir()

    assert transcriptions_dir.exists()
    assert transcriptions_dir.is_dir()
    assert transcriptions_dir == Path.home() / ".config" / "agent-cli" / "transcriptions"


def test_save_audio_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test saving audio data to a file."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    logger = MagicMock()
    audio_data = b"test_audio_data" * 100

    # Save the audio
    saved_path = asr._save_audio_to_file(audio_data, logger)

    # Verify the file was saved
    assert saved_path is not None
    assert saved_path.exists()
    assert saved_path.suffix == ".wav"
    assert saved_path.name.startswith("recording_")

    # Verify the logger was called
    logger.info.assert_called_once()
    assert "Saved audio recording to" in logger.info.call_args[0][0]


def test_save_audio_to_file_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error handling when saving audio fails."""
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    logger = MagicMock()
    audio_data = b"test_audio_data"

    # Try to save the audio (should fail gracefully)
    # We patch wave.open to simulate an error, which avoids creating a broken
    # Wave_write object that triggers warnings during garbage collection.
    with patch("agent_cli.services.asr.wave.open", side_effect=OSError("Mocked failure")):
        saved_path = asr._save_audio_to_file(audio_data, logger)

    # Verify it returned None and logged the exception
    assert saved_path is None
    logger.exception.assert_called_once()
    assert "Failed to save audio recording" in logger.exception.call_args[0][0]


def test_get_last_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test getting the most recent recording."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Create some test recording files with different timestamps
    test_files = [
        tmp_path / "recording_20240101_120000_000.wav",
        tmp_path / "recording_20240101_130000_000.wav",
        tmp_path / "recording_20240101_110000_000.wav",
    ]

    for filepath in test_files:
        filepath.touch()

    # Get the last recording (default, most recent)
    last_recording = asr.get_last_recording()
    assert last_recording == test_files[1]  # 130000 is the latest

    # Get the most recent explicitly
    last_recording = asr.get_last_recording(1)
    assert last_recording == test_files[1]  # 130000 is the latest

    # Get the second-to-last recording
    second_last = asr.get_last_recording(2)
    assert second_last == test_files[0]  # 120000 is second

    # Get the third-to-last recording
    third_last = asr.get_last_recording(3)
    assert third_last == test_files[2]  # 110000 is third

    # Try to get a recording that doesn't exist (4th)
    non_existent = asr.get_last_recording(4)
    assert non_existent is None

    # Try with invalid index
    invalid = asr.get_last_recording(0)
    assert invalid is None

    invalid = asr.get_last_recording(-1)
    assert invalid is None


def test_get_last_recording_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test getting the last recording when no files exist."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Get the last recording (should be None)
    last_recording = asr.get_last_recording()

    assert last_recording is None


def test_load_audio_from_file(tmp_path: Path):
    """Test loading audio data from a WAV file."""
    logger = MagicMock()

    # Create a test WAV file
    test_file = tmp_path / "test.wav"
    create_test_wav_file(test_file, duration_seconds=0.5)

    # Load the audio
    audio_data = asr.load_audio_from_file(test_file, logger)

    # Verify the audio was loaded
    assert audio_data is not None
    assert len(audio_data) > 0
    # 0.5 seconds * 16000 Hz * 2 bytes per sample = 16000 bytes
    assert len(audio_data) == int(0.5 * constants.AUDIO_RATE * 2)

    # Verify the logger was called
    logger.info.assert_called_once()
    # The logging uses %s formatting, not f-strings
    assert "Loaded PCM audio from" in logger.info.call_args[0][0]


def test_load_audio_from_file_not_found(tmp_path: Path):
    """Test error handling when loading a non-existent file."""
    logger = MagicMock()

    non_existent_file = tmp_path / "non_existent.wav"

    # Try to load the audio (should fail gracefully)
    audio_data = asr.load_audio_from_file(non_existent_file, logger)

    # Verify it returned None and logged the exception
    assert audio_data is None
    logger.exception.assert_called_once()
    # Check that the error message was logged (format string is evaluated at call time)
    assert "Failed to load audio from" in logger.exception.call_args[0][0]


def test_load_audio_from_file_raw_bytes(tmp_path: Path):
    """Test loading audio without PCM conversion (for OpenAI/Gemini native formats)."""
    logger = MagicMock()

    # Create a fake MP3 file (just raw bytes, not actual MP3)
    test_file = tmp_path / "test.mp3"
    test_content = b"fake mp3 content for testing"
    test_file.write_bytes(test_content)

    # Load without conversion
    audio_data = asr.load_audio_from_file(test_file, logger, convert_to_pcm=False)

    assert audio_data == test_content
    logger.info.assert_called_once()
    assert "Loaded raw audio from" in logger.info.call_args[0][0]


def test_load_audio_from_file_non_wav_no_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test loading non-WAV file when ffmpeg is not available."""
    logger = MagicMock()

    # Create a fake MP3 file
    test_file = tmp_path / "test.mp3"
    test_file.write_bytes(b"fake mp3")

    # Mock check_ffmpeg_available to return False
    monkeypatch.setattr("agent_cli.services.asr.check_ffmpeg_available", lambda: False)

    # Try to load with PCM conversion (should fail)
    audio_data = asr.load_audio_from_file(test_file, logger, convert_to_pcm=True)

    assert audio_data is None
    logger.error.assert_called_once()
    assert "ffmpeg not found" in logger.error.call_args[0][0]


@pytest.mark.asyncio
@patch("agent_cli.services.asr.read_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
@patch("agent_cli.services.asr.open_audio_stream")
async def test_record_audio_with_manual_stop_saves_recording(
    mock_open_audio_stream: MagicMock,
    mock_setup_input_stream: MagicMock,
    mock_read_audio_stream: AsyncMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that record_audio_with_manual_stop saves the recording when requested."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock stream
    mock_stream = MockSoundDeviceStream(input=True)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    mock_setup_input_stream.return_value = {"dtype": "int16"}

    # Simulate read_audio_stream writing to the buffer
    async def side_effect(chunk_handler: Any, **kwargs: Any) -> None:  # noqa: ARG001
        # chunk_handler is the buffer_chunk function from record_audio_with_manual_stop
        chunk_handler(b"audio_chunk" * 100)

    mock_read_audio_stream.side_effect = side_effect

    # Create a stop event
    stop_event = MagicMock()
    logger = MagicMock()

    # Record audio with saving enabled
    audio_data = await asr.record_audio_with_manual_stop(
        input_device_index=None,
        stop_event=stop_event,
        logger=logger,
        quiet=True,
        live=None,
        save_recording=True,
    )

    # Verify audio was recorded
    assert audio_data == b"audio_chunk" * 100

    # Verify a recording file was saved
    recordings = list(tmp_path.glob("recording_*.wav"))
    assert len(recordings) == 1


@pytest.mark.asyncio
@patch("agent_cli.services.asr.read_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
@patch("agent_cli.services.asr.open_audio_stream")
async def test_record_audio_with_manual_stop_no_save(
    mock_open_audio_stream: MagicMock,
    mock_setup_input_stream: MagicMock,
    mock_read_audio_stream: AsyncMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that record_audio_with_manual_stop doesn't save when save_recording=False."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock stream
    mock_stream = MockSoundDeviceStream(input=True)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    mock_setup_input_stream.return_value = {"dtype": "int16"}

    # Simulate read_audio_stream writing to the buffer
    async def side_effect(chunk_handler: Any, **kwargs: Any) -> None:  # noqa: ARG001
        chunk_handler(b"audio_chunk" * 100)

    mock_read_audio_stream.side_effect = side_effect

    # Create a stop event
    stop_event = MagicMock()
    logger = MagicMock()

    # Record audio with saving disabled
    audio_data = await asr.record_audio_with_manual_stop(
        input_device_index=None,
        stop_event=stop_event,
        logger=logger,
        quiet=True,
        live=None,
        save_recording=False,
    )

    # Verify audio was recorded
    assert audio_data == b"audio_chunk" * 100

    # Verify no recording file was saved
    recordings = list(tmp_path.glob("recording_*.wav"))
    assert len(recordings) == 0


@pytest.mark.asyncio
@patch("agent_cli.services.asr.read_audio_stream")
async def test_send_audio_with_save_recording(
    mock_read_audio_stream: AsyncMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that _send_audio saves the recording when requested."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock client and stream
    client = AsyncMock()
    stream = MagicMock()

    # Simulate read_audio_stream calls chunk_handler (send_chunk)
    async def side_effect(chunk_handler: Any, **kwargs: Any) -> None:  # noqa: ARG001
        await chunk_handler(b"audio_chunk")

    mock_read_audio_stream.side_effect = side_effect

    stop_event = MagicMock()
    logger = MagicMock()

    # Send audio with saving enabled
    await asr._send_audio(
        client=client,
        stream=stream,
        stop_event=stop_event,
        logger=logger,
        live=MagicMock(),
        quiet=False,
        save_recording=True,
    )

    # Verify events were sent
    # client.write_event called:
    # 1. Transcribe()
    # 2. AudioStart()
    # 3. AudioChunk()
    # 4. AudioStop()
    assert client.write_event.call_count >= 4

    # Verify a recording file was saved
    recordings = list(tmp_path.glob("recording_*.wav"))
    assert len(recordings) == 1


@pytest.mark.asyncio
async def test_transcribe_live_audio_wyoming_with_save():
    """Test that Wyoming transcription passes save_recording parameter."""
    with (
        patch("agent_cli.services.asr.wyoming_client_context") as mock_context,
        patch("agent_cli.services.asr.open_audio_stream"),
        patch("agent_cli.services.asr.setup_input_stream"),
        patch("agent_cli.services.asr.manage_send_receive_tasks") as mock_manage,
        patch("agent_cli.services.asr._send_audio") as mock_send,
    ):
        # Setup mocks
        mock_client = AsyncMock()
        mock_context.return_value.__aenter__.return_value = mock_client

        mock_recv_task = MagicMock()
        mock_recv_task.result = MagicMock(return_value="test transcript")
        mock_manage.return_value = (None, mock_recv_task)

        # Call the function with proper config objects
        result = await asr._transcribe_live_audio_wyoming(
            audio_input_cfg=config.AudioInput(input_device_index=None),
            wyoming_asr_cfg=config.WyomingASR(
                asr_wyoming_ip="localhost",
                asr_wyoming_port=10300,
            ),
            logger=MagicMock(),
            stop_event=MagicMock(),
            live=MagicMock(),
            quiet=False,
            save_recording=True,
        )

        # Verify save_recording was passed to _send_audio
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["save_recording"] is True
        assert result == "test transcript"


@pytest.mark.asyncio
async def test_transcribe_live_audio_buffered_with_save():
    """Test that buffered transcription passes save_recording parameter."""
    with patch("agent_cli.services.asr.record_audio_with_manual_stop") as mock_record:
        # Setup mocks
        mock_record.return_value = b"audio_data"
        mock_transcribe = AsyncMock(return_value="test transcript")

        # Call the buffered function
        result = await asr._transcribe_live_audio_buffered(
            audio_input_cfg=config.AudioInput(input_device_index=None),
            transcribe_fn=mock_transcribe,
            transcribe_cfg=config.OpenAIASR(
                asr_openai_model="whisper-1",
                openai_api_key="test-key",
            ),
            provider_name="OpenAI",
            logger=MagicMock(),
            stop_event=MagicMock(),
            live=MagicMock(),
            quiet=False,
            save_recording=True,
        )

        # Verify save_recording was passed to record_audio_with_manual_stop
        mock_record.assert_called_once()
        assert mock_record.call_args.kwargs["save_recording"] is True
        assert result == "test transcript"
