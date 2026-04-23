"""Tests for the retroactive transcribe-live diarization helper."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_cli.agents.diarize_live_session import (
    LiveSegment,
    align_logged_segments_with_speakers,
    build_logged_transcript,
    build_transcribe_command,
    parse_args,
    parse_clock_time,
    select_segments_in_range,
    session_basename,
    transcript_suffix,
)
from agent_cli.core.alignment import AlignedWord
from agent_cli.core.diarization import DiarizedSegment


def _segment(ts: str, filename: str) -> LiveSegment:
    return LiveSegment(
        timestamp=datetime.fromisoformat(ts),
        audio_file=Path(filename),
        duration_seconds=1.0,
    )


def test_parse_clock_time_accepts_minute_and_second_precision() -> None:
    assert parse_clock_time("11:32").isoformat() == "11:32:00"
    assert parse_clock_time("11:32:45").isoformat() == "11:32:45"


def test_parse_args_rejects_conflicting_speaker_hints() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--start", "11:32", "--end", "12:29", "--speakers", "3", "--min-speakers", "2"])


def test_select_segments_in_range_filters_by_date_and_time() -> None:
    segments = [
        _segment("2026-04-23T11:31:59-07:00", "before.mp3"),
        _segment("2026-04-23T11:32:00-07:00", "start.mp3"),
        _segment("2026-04-23T12:00:00-07:00", "middle.mp3"),
        _segment("2026-04-23T12:29:00-07:00", "end.mp3"),
        _segment("2026-04-23T12:29:01-07:00", "after.mp3"),
        _segment("2026-04-24T12:00:00-07:00", "other-date.mp3"),
    ]

    selected = select_segments_in_range(
        segments,
        target_date=date.fromisoformat("2026-04-23"),
        start_time=parse_clock_time("11:32"),
        end_time=parse_clock_time("12:29"),
    )

    assert [segment.audio_file.name for segment in selected] == [
        "start.mp3",
        "middle.mp3",
        "end.mp3",
    ]


def test_session_basename_uses_selected_time_range() -> None:
    segments = [
        _segment("2026-04-23T11:32:00-07:00", "one.mp3"),
        _segment("2026-04-23T12:29:00-07:00", "two.mp3"),
    ]

    assert session_basename(segments) == "live_20260423_113200_122900"


def test_build_logged_transcript_concatenates_non_empty_segment_text() -> None:
    segments = [
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:00-07:00"),
            audio_file=Path("one.mp3"),
            duration_seconds=1.0,
            raw_output="Hello there.",
        ),
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:33:00-07:00"),
            audio_file=Path("two.mp3"),
            duration_seconds=1.0,
            raw_output="  General Kenobi!  ",
        ),
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:34:00-07:00"),
            audio_file=Path("three.mp3"),
            duration_seconds=1.0,
            raw_output=None,
        ),
    ]

    assert build_logged_transcript(segments) == "Hello there. General Kenobi!"


def test_build_transcribe_command_uses_json_output_and_speaker_hints() -> None:
    args = parse_args(
        [
            "--start",
            "11:32",
            "--end",
            "12:29",
            "--speakers",
            "3",
            "--align-words",
            "--diarize-format",
            "json",
            "--hf-token",
            "token",
        ],
    )

    cmd = build_transcribe_command(args, Path("meeting.wav"))

    assert cmd[0].endswith("python")
    assert cmd[1:] == [
        "-m",
        "agent_cli",
        "transcribe",
        "--from-file",
        "meeting.wav",
        "--diarize",
        "--diarize-format",
        "json",
        "--json",
        "--min-speakers",
        "3",
        "--max-speakers",
        "3",
        "--align-words",
        "--align-language",
        "en",
        "--hf-token",
        "token",
    ]


def test_transcript_suffix_matches_diarize_format() -> None:
    assert transcript_suffix("inline") == ".txt"
    assert transcript_suffix("json") == ".json"


def test_align_logged_segments_with_speakers_offsets_words_per_chunk() -> None:
    segments = [
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:00-07:00"),
            audio_file=Path("one.mp3"),
            duration_seconds=2.0,
            raw_output="hello there",
        ),
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:05-07:00"),
            audio_file=Path("two.mp3"),
            duration_seconds=3.0,
            raw_output="general kenobi",
        ),
    ]
    speaker_segments = [
        DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.5),
        DiarizedSegment(speaker="SPEAKER_01", start=2.5, end=5.5),
    ]

    with patch(
        "agent_cli.agents.diarize_live_session.align",
        side_effect=[
            [
                AlignedWord(word="hello", start=0.0, end=0.4),
                AlignedWord(word="there", start=0.4, end=0.8),
            ],
            [
                AlignedWord(word="general", start=0.0, end=0.5),
                AlignedWord(word="kenobi", start=0.5, end=0.9),
            ],
        ],
    ):
        result = align_logged_segments_with_speakers(
            segments=segments,
            speaker_segments=speaker_segments,
        )

    assert [segment.speaker for segment in result] == ["SPEAKER_00", "SPEAKER_01"]
    assert result[0].text == "hello there general"
    assert result[1].text == "kenobi"
