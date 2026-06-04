"""Unit tests for the asr module."""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import suppress
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.asr import Transcribe, Transcript, TranscriptChunk
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import config
from agent_cli.services import asr, transcribe_audio_gemini, transcribe_audio_openai

if TYPE_CHECKING:
    from pathlib import Path


def test_write_live_preview_event(tmp_path: Path) -> None:
    """Test that live preview events are written as JSONL."""
    log_file = tmp_path / "preview.jsonl"

    asr._write_live_preview_event(
        log_file,
        event_type="partial",
        revision=1,
        text="hello world",
    )

    entry = json.loads(log_file.read_text().strip())
    assert entry["type"] == "partial"
    assert entry["revision"] == 1
    assert entry["text"] == "hello world"
    assert entry["is_final"] is False
    assert "timestamp" in entry


def test_print_live_preview_event(capsys: pytest.CaptureFixture[str]) -> None:
    """Test that live preview events can be printed to the terminal."""
    asr._print_live_preview_event(
        event_type="partial",
        revision=3,
        text="hello terminal",
    )

    captured = capsys.readouterr()
    assert "live #3:" in captured.err
    assert "hello terminal" in captured.err


@pytest.mark.asyncio
async def test_live_preview_streamer_emits_unique_partials(tmp_path: Path) -> None:
    """Test that rolling previews write changed transcript revisions."""
    log_file = tmp_path / "preview.jsonl"
    preview = asr.LivePreviewStreamer(
        asr.LivePreviewConfig(
            log_file=log_file,
            interval_seconds=60,
            window_seconds=1,
            min_audio_seconds=0,
        ),
        wyoming_asr_cfg=config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300),
        logger=MagicMock(),
    )
    preview.reset_log()

    with patch(
        "agent_cli.services.asr._transcribe_recorded_audio_wyoming",
        new_callable=AsyncMock,
        return_value="hello world",
    ):
        await preview.add_chunk(b"\x00\x00" * 160)
        await preview.emit_partial()
        await preview.emit_partial()

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert len(entries) == 1
    assert entries[0]["type"] == "partial"
    assert entries[0]["text"] == "hello world"


@pytest.mark.asyncio
async def test_live_preview_streamer_can_emit_console_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that rolling previews can be printed without a log file."""
    preview = asr.LivePreviewStreamer(
        asr.LivePreviewConfig(
            log_file=None,
            interval_seconds=60,
            window_seconds=1,
            min_audio_seconds=0,
            console=True,
        ),
        wyoming_asr_cfg=config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300),
        logger=MagicMock(),
    )

    with patch(
        "agent_cli.services.asr._transcribe_recorded_audio_wyoming",
        new_callable=AsyncMock,
        return_value="hello console",
    ):
        await preview.add_chunk(b"\x00\x00" * 160)
        await preview.emit_partial()

    captured = capsys.readouterr()
    assert "live #1:" in captured.err
    assert "hello console" in captured.err


@pytest.mark.asyncio
async def test_live_preview_streamer_stop_writes_final(tmp_path: Path) -> None:
    """Test that the final transcript is written to the preview log."""
    log_file = tmp_path / "preview.jsonl"
    preview = asr.LivePreviewStreamer(
        asr.LivePreviewConfig(log_file=log_file),
        wyoming_asr_cfg=config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300),
        logger=MagicMock(),
    )
    preview.reset_log()

    await preview.stop("final words")

    entry = json.loads(log_file.read_text().strip())
    assert entry["type"] == "final"
    assert entry["text"] == "final words"
    assert entry["is_final"] is True


@pytest.mark.asyncio
async def test_live_preview_streamer_ignores_partial_after_stop(tmp_path: Path) -> None:
    """A stale partial must not be appended after the final transcript."""
    log_file = tmp_path / "preview.jsonl"
    preview = asr.LivePreviewStreamer(
        asr.LivePreviewConfig(log_file=log_file),
        wyoming_asr_cfg=config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300),
        logger=MagicMock(),
    )
    preview.reset_log()
    await preview.add_chunk(b"\x00\x00" * 16_000)
    await preview.stop("final words")

    with patch(
        "agent_cli.services.asr._transcribe_recorded_audio_wyoming",
        new_callable=AsyncMock,
        return_value="stale partial",
    ):
        await preview.emit_partial()

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [entry["type"] for entry in entries] == ["final"]


@pytest.mark.asyncio
async def test_live_preview_run_cancel_drops_resolved_partial_before_final(
    tmp_path: Path,
) -> None:
    """A resolved preview response must not publish after the run task is canceled."""
    log_file = tmp_path / "preview.jsonl"
    preview = asr.LivePreviewStreamer(
        asr.LivePreviewConfig(log_file=log_file, interval_seconds=0.01),
        wyoming_asr_cfg=config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300),
        logger=MagicMock(),
    )
    preview.reset_log()
    await preview.add_chunk(b"\x00\x00" * 16_000)

    entered_transcription = asyncio.Event()
    transcription_result: asyncio.Future[str] = asyncio.Future()

    async def transcribe_after_signal(**_kwargs: object) -> str:
        entered_transcription.set()
        return await transcription_result

    with patch(
        "agent_cli.services.asr._transcribe_recorded_audio_wyoming",
        side_effect=transcribe_after_signal,
    ):
        task = asyncio.create_task(preview.run())
        await asyncio.wait_for(entered_transcription.wait(), timeout=1)
        transcription_result.set_result("stale partial")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    await preview.stop("final words")

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [entry["type"] for entry in entries] == ["final"]
    assert entries[0]["text"] == "final words"


@pytest.mark.asyncio
async def test_send_audio() -> None:
    """Test that _send_audio sends the correct events."""
    # Arrange
    client = AsyncMock()
    stream = MagicMock()
    stop_event = MagicMock()
    stop_event.is_set.side_effect = [False, True]  # Allow one iteration then stop
    stop_event.ctrl_c_pressed = False

    mock_data = MagicMock()
    mock_data.tobytes.return_value = b"fake_audio_chunk"
    stream.read.return_value = (mock_data, False)
    logger = MagicMock()
    levels: list[bytes] = []

    # Act
    # No need to create a task and sleep, just await the coroutine.
    # The side_effect will stop the loop.
    await asr._send_audio(
        client,
        stream,
        stop_event,
        logger,
        live=MagicMock(),
        quiet=False,
        save_recording=False,
        audio_level_callback=levels.append,
    )

    # Assert
    assert client.write_event.call_count == 4
    client.write_event.assert_any_call(Transcribe().event())
    client.write_event.assert_any_call(
        AudioStart(rate=16000, width=2, channels=1).event(),
    )
    client.write_event.assert_any_call(
        AudioChunk(
            rate=16000,
            width=2,
            channels=1,
            audio=b"fake_audio_chunk",
        ).event(),
    )
    client.write_event.assert_any_call(AudioStop().event())
    assert levels == [b"fake_audio_chunk"]


@pytest.mark.asyncio
async def test_send_audio_does_not_wait_for_audio_level_callback() -> None:
    """Test that level callbacks cannot block audio delivery to Wyoming."""
    client = AsyncMock()
    stream = MagicMock()
    stop_event = MagicMock()
    stop_event.is_set.side_effect = [False, True]
    stop_event.ctrl_c_pressed = False

    mock_data = MagicMock()
    mock_data.tobytes.return_value = b"fake_audio_chunk"
    stream.read.return_value = (mock_data, False)
    logger = MagicMock()
    callback_started = threading.Event()
    release_callback = threading.Event()

    def slow_audio_level_callback(_chunk: bytes) -> None:
        callback_started.set()
        release_callback.wait(timeout=2)

    send_task = asyncio.create_task(
        asr._send_audio(
            client,
            stream,
            stop_event,
            logger,
            live=MagicMock(),
            quiet=False,
            save_recording=False,
            audio_level_callback=slow_audio_level_callback,
        ),
    )

    try:
        for _ in range(100):
            if callback_started.is_set() and client.write_event.call_count >= 3:
                break
            await asyncio.sleep(0.01)

        assert callback_started.is_set()
        assert client.write_event.call_count >= 3
        assert not send_task.done()
    finally:
        release_callback.set()

    await asyncio.wait_for(send_task, timeout=2)


@pytest.mark.asyncio
async def test_receive_text() -> None:
    """Test that receive_transcript correctly processes events."""
    # Arrange
    client = AsyncMock()
    client.read_event.side_effect = [
        TranscriptChunk(text="hello").event(),
        Transcript(text="hello world").event(),
        None,  # To stop the loop
    ]
    logger = MagicMock()
    chunk_callback = MagicMock()
    final_callback = MagicMock()

    # Act
    result = await asr._receive_transcript(
        client,
        logger,
        chunk_callback=chunk_callback,
        final_callback=final_callback,
    )

    # Assert
    assert result == "hello world"
    chunk_callback.assert_called_once_with("hello")
    final_callback.assert_called_once_with("hello world")


def test_create_transcriber():
    """Test that the correct transcriber is returned."""
    provider_cfg = MagicMock()

    # OpenAI uses generic transcriber with transcribe_audio_openai
    provider_cfg.asr_provider = "openai"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_buffered
    assert transcriber.keywords["transcribe_fn"] is transcribe_audio_openai

    # Wyoming uses its own streaming implementation
    provider_cfg.asr_provider = "wyoming"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_wyoming

    # Gemini uses generic transcriber with transcribe_audio_gemini
    provider_cfg.asr_provider = "gemini"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_buffered
    assert transcriber.keywords["transcribe_fn"] is transcribe_audio_gemini


def test_create_recorded_audio_transcriber():
    """Test that the correct recorded audio transcriber is returned."""
    provider_cfg = MagicMock()
    provider_cfg.asr_provider = "openai"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr.transcribe_audio_openai

    provider_cfg.asr_provider = "wyoming"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr._transcribe_recorded_audio_wyoming

    provider_cfg.asr_provider = "gemini"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr.transcribe_audio_gemini


@pytest.mark.asyncio
@patch("agent_cli.services.asr.wyoming_client_context", side_effect=ConnectionRefusedError)
async def test_transcribe_recorded_audio_wyoming_connection_error(
    mock_wyoming_client_context: MagicMock,
):
    """Test that transcribe_recorded_audio_wyoming handles ConnectionRefusedError."""
    result = await asr._transcribe_recorded_audio_wyoming(
        audio_data=b"test",
        wyoming_asr_cfg=MagicMock(),
        logger=MagicMock(),
    )
    assert result == ""
    mock_wyoming_client_context.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services._get_gemini_client")
async def test_transcribe_audio_gemini_success(mock_get_gemini_client: MagicMock):
    """Test that transcribe_audio_gemini calls the Gemini API correctly."""
    # Setup mock client and response
    mock_client = MagicMock()
    mock_get_gemini_client.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "  hello world  "  # With whitespace to test strip()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )

    # Test with WAV data (starts with RIFF header)
    wav_data = b"RIFF\x00\x00\x00\x00WAVEfmt test audio data"
    with patch("agent_cli.services._gemini_types_module") as mock_get_types:
        result = await transcribe_audio_gemini(
            audio_data=wav_data,
            gemini_asr_cfg=gemini_asr_cfg,
            logger=MagicMock(),
        )

    assert result == "hello world"  # Should be stripped
    mock_get_gemini_client.assert_called_once_with("test-key")
    mock_client.aio.models.generate_content.assert_called_once()
    mock_get_types.return_value.Part.from_bytes.assert_called_once()

    # Verify the model parameter
    call_args = mock_client.aio.models.generate_content.call_args
    assert call_args.kwargs["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
@patch("agent_cli.services._get_gemini_client")
async def test_transcribe_audio_gemini_converts_pcm_to_wav(
    mock_get_gemini_client: MagicMock,
):
    """Test that transcribe_audio_gemini auto-converts PCM to WAV."""
    mock_client = MagicMock()
    mock_get_gemini_client.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "transcribed text"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )

    # Test with raw PCM data (no RIFF header)
    pcm_data = b"\x00\x00\x01\x00" * 100
    with patch("agent_cli.services._gemini_types_module") as mock_get_types:
        result = await transcribe_audio_gemini(
            audio_data=pcm_data,
            gemini_asr_cfg=gemini_asr_cfg,
            logger=MagicMock(),
        )

    assert result == "transcribed text"

    # Verify the audio was converted to WAV (check the Part.from_bytes call)
    audio_part_call = mock_get_types.return_value.Part.from_bytes.call_args
    assert audio_part_call.kwargs["mime_type"] == "audio/wav"
    # The data should now be WAV format (starts with RIFF)
    assert audio_part_call.kwargs["data"][:4] == b"RIFF"


@pytest.mark.asyncio
async def test_transcribe_audio_gemini_missing_api_key():
    """Test that transcribe_audio_gemini raises error when API key is missing."""
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key=None,
    )

    with pytest.raises(ValueError, match="Gemini API key is not set"):
        await transcribe_audio_gemini(
            audio_data=b"test audio",
            gemini_asr_cfg=gemini_asr_cfg,
            logger=MagicMock(),
        )
