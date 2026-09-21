"""Tests for the shared WAV-container preparation used by file-path backends."""

from __future__ import annotations

import asyncio
import io
import shutil
import wave
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from agent_cli.server.whisper.backends import audio as audio_preparation
from agent_cli.server.whisper.backends.audio import prepare_wav_audio
from agent_cli.server.whisper.backends.base import InvalidAudioError

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.asyncio


def _create_test_wav(*, width: int = 2, channels: int = 1, rate: int = 16000) -> bytes:
    """Create a tiny valid WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(width)
        wav_file.setframerate(rate)
        wav_file.writeframes(bytes(width * channels * 160))
    return buffer.getvalue()


async def test_prepare_wav_audio_keeps_valid_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real WAV upload must be handed through without an FFmpeg round-trip."""
    audio = _create_test_wav()
    monkeypatch.setattr(
        audio_preparation,
        "convert_audio_to_wav_format",
        lambda *_args, **_kwargs: pytest.fail("unexpected conversion"),
    )

    assert await prepare_wav_audio(audio, "sample.wav", backend_label="test backend") is audio


@pytest.mark.parametrize(
    ("payload", "filename"),
    [
        (b"\x00\x00\x00 ftypM4A ", "voice.m4a"),
        (b"OggS\x00\x02", "voice.ogg"),
    ],
)
async def test_prepare_wav_audio_converts_non_wav(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    filename: str,
) -> None:
    """Non-WAV uploads are converted so the file-path parsers never see them."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    async def fake_convert(audio: bytes, source_filename: str) -> bytes:
        calls["audio"] = audio
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(audio_preparation, "convert_audio_to_wav_format", fake_convert)

    assert await prepare_wav_audio(payload, filename, backend_label="test backend") == converted
    assert calls == {"audio": payload, "source_filename": filename}


async def test_prepare_wav_audio_defaults_source_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploads without a filename still reach FFmpeg with a usable name."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    async def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(audio_preparation, "convert_audio_to_wav_format", fake_convert)

    assert await prepare_wav_audio(b"OggS", None, backend_label="test backend") == converted
    assert calls == {"source_filename": "audio"}


async def test_prepare_wav_audio_raises_invalid_audio_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversion failures become an actionable typed error, not a parser traceback."""

    async def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        msg = "FFmpeg not found in PATH."
        raise RuntimeError(msg)

    monkeypatch.setattr(audio_preparation, "convert_audio_to_wav_format", fake_convert)

    with pytest.raises(InvalidAudioError, match="Unsupported audio format for test backend"):
        await prepare_wav_audio(b"not audio", "voice.m4a", backend_label="test backend")


@pytest.mark.parametrize(
    ("width", "channels", "rate"),
    [(1, 1, 16000), (3, 1, 16000), (4, 1, 16000), (2, 2, 16000), (2, 1, 44100)],
)
async def test_normalizes_wav_samples_for_model(width: int, channels: int, rate: int) -> None:
    """Passing unsupported WAV samples through corrupts Transformers' int16 mono input."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found")
    audio = _create_test_wav(width=width, channels=channels, rate=rate)

    converted = await prepare_wav_audio(audio, "voice.wav", backend_label="test backend")

    with wave.open(io.BytesIO(converted), "rb") as wav_file:
        assert (wav_file.getsampwidth(), wav_file.getnchannels(), wav_file.getframerate()) == (
            2,
            1,
            16000,
        )
        assert wav_file.getnframes() == (58 if rate == 44100 else 160)


@pytest.mark.parametrize("filename", ["voice.m4a", "voice.ogg", "voice.mp3"])
async def test_prepares_real_compressed_audio(tmp_path: Path, filename: str) -> None:
    """Exercise FFmpeg and the WAV parser together so mocked conversions cannot hide failures."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not found")
    assert ffmpeg is not None
    source = tmp_path / filename
    process = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "pipe:0",
        str(source),
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate(_create_test_wav())
    assert process.returncode == 0, stderr

    converted = await prepare_wav_audio(source.read_bytes(), filename, backend_label="test backend")

    with wave.open(io.BytesIO(converted), "rb") as wav_file:
        assert (wav_file.getsampwidth(), wav_file.getnchannels(), wav_file.getframerate()) == (
            2,
            1,
            16000,
        )
        assert wav_file.readframes(wav_file.getnframes())


async def test_malformed_riff_raises_invalid_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """An oversized RIFF chunk raises RuntimeError in wave's seek, not wave.Error."""
    audio = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEJUNK" + (100000).to_bytes(4, "little")
    monkeypatch.setattr(
        audio_preparation,
        "convert_audio_to_wav_format",
        AsyncMock(side_effect=RuntimeError("invalid input")),
    )

    with pytest.raises(InvalidAudioError):
        await prepare_wav_audio(audio, "voice.wav", backend_label="test backend")
