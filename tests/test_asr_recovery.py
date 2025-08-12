"""Tests for the ASR recovery features."""

from __future__ import annotations

import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config, constants
from agent_cli.services import asr


def create_test_wav_file(filepath: Path, duration_seconds: float = 1.0) -> None:
    """Create a test WAV file with silence."""
    sample_rate = constants.PYAUDIO_RATE
    channels = constants.PYAUDIO_CHANNELS
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
    # Monkeypatch to return a read-only directory
    read_only_dir = tmp_path / "readonly"
    read_only_dir.mkdir(mode=0o444)
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: read_only_dir / "nonexistent")

    logger = MagicMock()
    audio_data = b"test_audio_data"

    # Try to save the audio (should fail gracefully)
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
    assert len(audio_data) == int(0.5 * constants.PYAUDIO_RATE * 2)

    # Verify the logger was called
    logger.info.assert_called_once()
    # The logging uses %s formatting, not f-strings
    assert "Loaded audio from" in logger.info.call_args[0][0]


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


@pytest.mark.asyncio
async def test_record_audio_with_manual_stop_saves_recording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that record_audio_with_manual_stop saves the recording when requested."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock PyAudio and stream
    mock_p = MagicMock()
    mock_stream = MagicMock()
    mock_stream.read.return_value = b"audio_chunk" * 100

    # Mock the open_pyaudio_stream context manager
    with patch("agent_cli.services.asr.open_pyaudio_stream") as mock_open_stream:
        mock_open_stream.return_value.__enter__.return_value = mock_stream

        # Create a stop event that stops after one iteration
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]

        logger = MagicMock()

        # Record audio with saving enabled
        audio_data = await asr.record_audio_with_manual_stop(
            p=mock_p,
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
async def test_record_audio_with_manual_stop_no_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that record_audio_with_manual_stop doesn't save when save_recording=False."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock PyAudio and stream
    mock_p = MagicMock()
    mock_stream = MagicMock()
    mock_stream.read.return_value = b"audio_chunk" * 100

    # Mock the open_pyaudio_stream context manager
    with patch("agent_cli.services.asr.open_pyaudio_stream") as mock_open_stream:
        mock_open_stream.return_value.__enter__.return_value = mock_stream

        # Create a stop event that stops after one iteration
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]

        logger = MagicMock()

        # Record audio with saving disabled
        audio_data = await asr.record_audio_with_manual_stop(
            p=mock_p,
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
async def test_send_audio_with_save_recording(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that _send_audio saves the recording when requested."""
    # Monkeypatch the transcriptions directory to use tmp_path
    monkeypatch.setattr(asr, "_get_transcriptions_dir", lambda: tmp_path)

    # Mock client and stream
    client = AsyncMock()
    stream = MagicMock()
    stream.read.return_value = b"audio_chunk"

    # Create a stop event that stops after two iterations
    stop_event = MagicMock()
    stop_event.is_set.side_effect = [False, False, True]
    stop_event.ctrl_c_pressed = False

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
    assert client.write_event.call_count >= 4  # Start, chunks, stop

    # Verify a recording file was saved
    recordings = list(tmp_path.glob("recording_*.wav"))
    assert len(recordings) == 1


@pytest.mark.asyncio
async def test_transcribe_live_audio_wyoming_with_save():
    """Test that Wyoming transcription passes save_recording parameter."""
    with (
        patch("agent_cli.services.asr.wyoming_client_context") as mock_context,
        patch("agent_cli.services.asr.open_pyaudio_stream"),
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
            p=MagicMock(),
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
async def test_transcribe_live_audio_openai_with_save():
    """Test that OpenAI transcription passes save_recording parameter."""
    with (
        patch("agent_cli.services.asr.record_audio_with_manual_stop") as mock_record,
        patch("agent_cli.services.asr.transcribe_audio_openai") as mock_transcribe,
    ):
        # Setup mocks
        mock_record.return_value = b"audio_data"
        mock_transcribe.return_value = "test transcript"

        # Call the function with proper config objects
        result = await asr._transcribe_live_audio_openai(
            audio_input_cfg=config.AudioInput(input_device_index=None),
            openai_asr_cfg=config.OpenAIASR(
                asr_openai_model="whisper-1",
                openai_api_key="test-key",
            ),
            logger=MagicMock(),
            p=MagicMock(),
            stop_event=MagicMock(),
            live=MagicMock(),
            quiet=False,
            save_recording=True,
        )

        # Verify save_recording was passed to record_audio_with_manual_stop
        mock_record.assert_called_once()
        assert mock_record.call_args.kwargs["save_recording"] is True
        assert result == "test transcript"
