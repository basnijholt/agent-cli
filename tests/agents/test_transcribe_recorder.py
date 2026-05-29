"""Tests for the warm transcription recorder daemon."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from agent_cli.cli import app
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
