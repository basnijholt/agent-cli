"""Tests for the warm transcription recorder daemon."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.daemon import transcribe_recorder
from agent_cli.daemon.transcribe_recorder import WarmAudioBuffer

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def test_warm_audio_buffer_includes_preroll_on_stop() -> None:
    buffer = WarmAudioBuffer(max_preroll_chunks=2)

    buffer.add_chunk(b"old")
    buffer.add_chunk(b"pre1")
    buffer.add_chunk(b"pre2")

    assert buffer.start() == "started"
    buffer.add_chunk(b"live1")
    buffer.add_chunk(b"live2")

    assert buffer.stop() == b"pre1pre2live1live2"


def test_warm_audio_buffer_rejects_duplicate_start_and_empty_stop() -> None:
    buffer = WarmAudioBuffer(max_preroll_chunks=1)

    assert buffer.stop() is None
    assert buffer.start() == "started"
    assert buffer.start() == "already_recording"

    buffer.add_chunk(b"chunk")

    assert buffer.stop() == b"chunk"
    assert buffer.stop() is None


def test_json_client_error_is_machine_readable(tmp_path: Path) -> None:
    missing_socket = tmp_path / "missing.sock"

    result = runner.invoke(
        app,
        ["daemon", "transcribe-recorder", "status", "--socket", str(missing_socket), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "Transcribe daemon is not running",
        "socket_path": str(missing_socket),
    }


def test_json_client_error_handles_unsupported_unix_sockets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test unsupported Unix sockets still produce the JSON client error."""
    missing_socket = tmp_path / "missing.sock"

    async def fake_request(_socket_path: Path, _action: str) -> dict[str, object]:
        msg = "open_unix_connection is unavailable"
        raise AttributeError(msg)

    monkeypatch.setattr(transcribe_recorder, "_request", fake_request)

    result = runner.invoke(
        app,
        ["daemon", "transcribe-recorder", "status", "--socket", str(missing_socket), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "Transcribe daemon is not running",
        "socket_path": str(missing_socket),
    }


def test_json_client_timeout_is_machine_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test client timeouts produce a bounded JSON error."""
    socket_path = tmp_path / "daemon.sock"

    async def fake_request(_socket_path: Path, _action: str) -> dict[str, object]:
        msg = "request timed out"
        raise TimeoutError(msg)

    monkeypatch.setattr(transcribe_recorder, "_request", fake_request)

    result = runner.invoke(
        app,
        ["daemon", "transcribe-recorder", "status", "--socket", str(socket_path), "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "Transcribe daemon request timed out",
        "socket_path": str(socket_path),
    }


@pytest.mark.asyncio
async def test_stop_removes_temp_recording_when_write_wav_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test temp recordings are removed when WAV writing fails."""
    recording_path = tmp_path / "recording.wav"
    recording_path.write_bytes(b"partial")
    buffer = WarmAudioBuffer(max_preroll_chunks=1)
    assert buffer.start() == "started"
    buffer.add_chunk(b"audio")

    daemon = cast("Any", object.__new__(transcribe_recorder.TranscribeDaemon))
    daemon.recorder = SimpleNamespace(
        buffer=buffer,
        daemon_config=SimpleNamespace(save_recording=False),
    )

    def fail_write(_path: Path, _audio_data: bytes) -> None:
        msg = "disk full"
        raise OSError(msg)

    def fake_recording_path(**_kwargs: object) -> Path:
        return recording_path

    monkeypatch.setattr(transcribe_recorder, "_recording_path", fake_recording_path)
    monkeypatch.setattr(transcribe_recorder, "_write_wav", fail_write)

    with pytest.raises(OSError, match="disk full"):
        await daemon.stop()

    assert not recording_path.exists()


def test_serve_closes_daemon_when_unix_sockets_are_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test serve reports unsupported Unix sockets without leaking the recorder."""
    socket_path = tmp_path / "daemon.sock"
    closed = False

    class FakeDaemon:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            nonlocal closed
            closed = True

    async def fake_serve(_socket_path: Path, _daemon: object) -> None:
        msg = "Unix sockets are unavailable"
        raise NotImplementedError(msg)

    monkeypatch.setattr(asyncio, "start_unix_server", object(), raising=False)
    monkeypatch.setattr(transcribe_recorder, "TranscribeDaemon", FakeDaemon)
    monkeypatch.setattr(transcribe_recorder, "_serve", fake_serve)

    result = runner.invoke(
        app,
        ["daemon", "transcribe-recorder", "serve", "--socket", str(socket_path)],
    )

    assert result.exit_code == 1
    assert closed
