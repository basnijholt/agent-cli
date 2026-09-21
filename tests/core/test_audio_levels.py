"""Tests for recorder-backed voice level logging."""

from __future__ import annotations

import json
import struct
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agent_cli.core.audio import AudioLevelLogWriter, normalized_audio_level

if TYPE_CHECKING:
    from pathlib import Path


def _pcm_chunk(sample: int, count: int = 1024) -> bytes:
    return struct.pack(f"<{count}h", *([sample] * count))


def test_normalized_audio_level_tracks_pcm_energy() -> None:
    silence = _pcm_chunk(0)
    quiet = _pcm_chunk(1000)
    loud = _pcm_chunk(16000)

    assert normalized_audio_level(silence) == 0.0
    assert 0 < normalized_audio_level(quiet) < normalized_audio_level(loud) <= 1


def test_audio_level_log_writer_truncates_stale_file_and_appends_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "voice-levels.jsonl"
    log_path.write_text('{"level": 1.0}\n')
    writer = AudioLevelLogWriter(
        log_path,
        interval_seconds=0.0,
        monotonic_clock=lambda: 1.0,
        timestamp_clock=lambda: datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )

    writer.write_chunk(_pcm_chunk(12000))

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["timestamp"] == "2026-06-04T12:00:00+00:00"
    assert entry["level"] > 0.5
