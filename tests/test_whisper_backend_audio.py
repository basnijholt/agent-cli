"""Tests for the shared WAV-container preparation used by file-path backends."""

from __future__ import annotations

import io
import wave

import pytest

from agent_cli.server.whisper.backends import base
from agent_cli.server.whisper.backends.base import InvalidAudioError, ensure_wav_container


def _create_test_wav() -> bytes:
    """Create a tiny valid WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def test_ensure_wav_container_keeps_valid_wav(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real WAV upload must be handed through without an FFmpeg round-trip."""
    audio = _create_test_wav()
    monkeypatch.setattr(
        base,
        "convert_audio_to_wav_format",
        lambda *_args, **_kwargs: pytest.fail("unexpected conversion"),
    )

    assert ensure_wav_container(audio, "sample.wav", backend_label="test backend") is audio


@pytest.mark.parametrize(
    ("payload", "filename"),
    [
        (b"\x00\x00\x00 ftypM4A ", "voice.m4a"),
        (b"OggS\x00\x02", "voice.ogg"),
    ],
)
def test_ensure_wav_container_converts_non_wav(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    filename: str,
) -> None:
    """Non-WAV uploads are converted so the file-path parsers never see them."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    def fake_convert(audio: bytes, source_filename: str) -> bytes:
        calls["audio"] = audio
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(base, "convert_audio_to_wav_format", fake_convert)

    assert ensure_wav_container(payload, filename, backend_label="test backend") == converted
    assert calls == {"audio": payload, "source_filename": filename}


def test_ensure_wav_container_defaults_source_filename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploads without a filename still reach FFmpeg with a usable name."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(base, "convert_audio_to_wav_format", fake_convert)

    assert ensure_wav_container(b"OggS", None, backend_label="test backend") == converted
    assert calls == {"source_filename": "audio"}


def test_ensure_wav_container_raises_invalid_audio_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversion failures become an actionable typed error, not a parser traceback."""

    def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        msg = "FFmpeg not found in PATH."
        raise RuntimeError(msg)

    monkeypatch.setattr(base, "convert_audio_to_wav_format", fake_convert)

    with pytest.raises(InvalidAudioError, match="Unsupported audio format for test backend"):
        ensure_wav_container(b"not audio", "voice.m4a", backend_label="test backend")
