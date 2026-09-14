"""Tests for the faster-whisper backend."""

from __future__ import annotations

import io
import wave
from concurrent.futures.process import BrokenProcessPool
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest

from agent_cli.server.whisper.backends import base
from agent_cli.server.whisper.backends.base import BackendConfig, InvalidAudioError
from agent_cli.server.whisper.backends.faster_whisper import FasterWhisperBackend

if TYPE_CHECKING:
    from concurrent.futures import ProcessPoolExecutor


@pytest.mark.asyncio
async def test_faster_whisper_transcribe_recovers_from_broken_process_pool() -> None:
    """Reload the backend and retry once when the process pool is broken."""
    config = BackendConfig(model_name="tiny", device="cpu", compute_type="int8")
    backend = FasterWhisperBackend(config)
    initial_executor = cast("ProcessPoolExecutor", object())
    backend._executor = initial_executor
    backend._device = "cpu"

    recovered_executor = cast("ProcessPoolExecutor", object())
    fake_result = {
        "text": "hello world",
        "language": "en",
        "language_probability": 0.99,
        "duration": 1.25,
        "segments": [],
    }
    executors_seen: list[object] = []

    async def mock_run_in_executor(
        executor: object, _func: object, *_args: object
    ) -> dict[str, object]:
        executors_seen.append(executor)
        if len(executors_seen) == 1:
            msg = "worker died"
            raise BrokenProcessPool(msg)
        return fake_result

    async def fake_unload() -> None:
        backend._executor = None
        backend._device = None

    async def fake_load() -> float:
        backend._executor = recovered_executor
        backend._device = "cpu"
        return 0.1

    with (
        patch("asyncio.get_running_loop") as mock_loop,
        patch.object(backend, "unload", new=AsyncMock(side_effect=fake_unload)) as unload_mock,
        patch.object(backend, "load", new=AsyncMock(side_effect=fake_load)) as load_mock,
    ):
        mock_loop.return_value.run_in_executor = mock_run_in_executor
        result = await backend.transcribe(_create_test_wav())

    assert result.text == "hello world"
    unload_mock.assert_awaited_once()
    load_mock.assert_awaited_once()
    assert executors_seen == [initial_executor, recovered_executor]


def _create_test_wav() -> bytes:
    """Create a tiny valid 16kHz mono 16-bit WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


async def _transcribe_capturing_audio(audio: bytes, source_filename: str | None) -> bytes:
    """Run the backend against a stub executor and return the bytes it dispatched."""
    backend = FasterWhisperBackend(BackendConfig(model_name="tiny"))
    backend._executor = cast("ProcessPoolExecutor", object())
    dispatched: dict[str, bytes] = {}

    async def mock_run_in_executor(
        _executor: object,
        _func: object,
        audio_bytes: bytes,
        _kwargs: dict[str, object],
    ) -> dict[str, object]:
        dispatched["audio"] = audio_bytes
        return {
            "text": "hello",
            "language": "en",
            "language_probability": 1.0,
            "duration": 0.01,
            "segments": [],
        }

    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = mock_run_in_executor
        result = await backend.transcribe(audio, source_filename=source_filename)

    assert result.text == "hello"
    return dispatched["audio"]


@pytest.mark.asyncio
async def test_transcribe_converts_non_wav_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ogg upload must be transcoded before the worker writes its `.wav` temp file."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    def fake_convert(audio: bytes, source_filename: str) -> bytes:
        calls["audio"] = audio
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(base, "convert_audio_to_wav_format", fake_convert)

    assert await _transcribe_capturing_audio(b"OggS\x00\x02", "voice.ogg") == converted
    assert calls == {"audio": b"OggS\x00\x02", "source_filename": "voice.ogg"}


@pytest.mark.asyncio
async def test_transcribe_passes_wav_through_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real WAV upload must not pay for a pointless FFmpeg round-trip."""
    audio = _create_test_wav()
    monkeypatch.setattr(
        base,
        "convert_audio_to_wav_format",
        lambda *_args, **_kwargs: pytest.fail("unexpected conversion"),
    )

    assert await _transcribe_capturing_audio(audio, "voice.wav") == audio


@pytest.mark.asyncio
async def test_transcribe_reports_conversion_failure_as_invalid_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed conversion surfaces a typed error instead of a raw WAV parser traceback."""

    def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        msg = "FFmpeg not found in PATH."
        raise RuntimeError(msg)

    monkeypatch.setattr(base, "convert_audio_to_wav_format", fake_convert)
    backend = FasterWhisperBackend(BackendConfig(model_name="tiny"))
    backend._executor = cast("ProcessPoolExecutor", object())

    with pytest.raises(InvalidAudioError, match="Unsupported audio format for faster-whisper"):
        await backend.transcribe(b"\x00\x00\x00 ftypM4A ", source_filename="voice.m4a")
