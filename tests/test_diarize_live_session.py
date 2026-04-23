"""Tests for the retroactive transcribe-live diarization helper."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_cli.agents.diarize_live_session import (
    LiveSegment,
    align_logged_segments_with_speakers,
    build_logged_transcript,
    build_retranscribe_request,
    main,
    parse_args,
    parse_clock_time,
    run_retranscribe,
    select_segments_in_range,
    session_basename,
    transcript_suffix,
)
from agent_cli.core.alignment import AlignedWord
from agent_cli.core.diarization import DiarizedSegment


def _segment(ts: str, filename: str, *, duration_seconds: float = 1.0) -> LiveSegment:
    return LiveSegment(
        timestamp=datetime.fromisoformat(ts),
        audio_file=Path(filename),
        duration_seconds=duration_seconds,
    )


def test_parse_clock_time_accepts_minute_and_second_precision() -> None:
    assert parse_clock_time("11:32").isoformat() == "11:32:00"
    assert parse_clock_time("11:32:45").isoformat() == "11:32:45"


def test_parse_args_rejects_conflicting_speaker_hints() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--start", "11:32", "--end", "12:29", "--speakers", "3", "--min-speakers", "2"])


def test_select_segments_in_range_filters_by_date_and_time() -> None:
    segments = [
        _segment("2026-04-23T11:31:59-07:00", "before.mp3", duration_seconds=0.5),
        _segment("2026-04-23T11:32:02-07:00", "overlap-start.mp3", duration_seconds=5.0),
        _segment("2026-04-23T12:00:00-07:00", "middle.mp3"),
        _segment("2026-04-23T12:29:05-07:00", "overlap-end.mp3", duration_seconds=10.0),
        _segment("2026-04-23T12:29:10-07:00", "after.mp3", duration_seconds=0.5),
        _segment("2026-04-24T12:00:00-07:00", "other-date.mp3"),
    ]

    selected = select_segments_in_range(
        segments,
        target_date=date.fromisoformat("2026-04-23"),
        start_time=parse_clock_time("11:32"),
        end_time=parse_clock_time("12:29"),
    )

    assert [segment.audio_file.name for segment in selected] == [
        "overlap-start.mp3",
        "middle.mp3",
        "overlap-end.mp3",
    ]


def test_select_segments_in_range_uses_saved_audio_duration_when_available(
    tmp_path: Path,
) -> None:
    saved = tmp_path / "saved.mp3"
    saved.write_bytes(b"mp3")
    segments = [
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:01-07:00"),
            audio_file=saved,
            duration_seconds=0.2,
        ),
    ]

    with patch(
        "agent_cli.agents.diarize_live_session._saved_audio_duration_seconds",
        return_value=2.0,
    ):
        selected = select_segments_in_range(
            segments,
            target_date=date.fromisoformat("2026-04-23"),
            start_time=parse_clock_time("11:31:59"),
            end_time=parse_clock_time("11:32:00"),
        )

    assert [segment.audio_file.name for segment in selected] == ["saved.mp3"]


def test_run_retranscribe_uses_transcribe_config_defaults(tmp_path: Path) -> None:
    args = parse_args(
        [
            "--start",
            "11:32",
            "--end",
            "12:29",
            "--retranscribe",
            "--diarize-format",
            "json",
            "--hf-token",
            "token",
        ],
    )
    combined_audio = tmp_path / "meeting.wav"
    combined_audio.write_bytes(b"wav")
    transcript_path = tmp_path / "meeting.json"
    mock_async_main = AsyncMock(return_value={"transcript": '{"segments": []}'})

    with (
        patch(
            "agent_cli.agents.diarize_live_session.agent_config.load_config",
            return_value={
                "defaults": {"openai_api_key": "cfg-key"},
                "transcribe": {
                    "asr_provider": "openai",
                    "llm_provider": "openai",
                    "asr_openai_model": "gpt-4o-mini-transcribe",
                    "asr_openai_base_url": "https://asr.example/v1",
                    "llm_openai_model": "gpt-5-mini",
                },
            },
        ),
        patch("agent_cli.agents.transcribe._async_main", mock_async_main),
    ):
        run_retranscribe(
            args,
            combined_audio,
            transcript_path,
            config_file="custom.toml",
        )

    assert transcript_path.read_text(encoding="utf-8") == '{"segments": []}\n'
    assert mock_async_main.await_args is not None
    kwargs = mock_async_main.await_args.kwargs
    assert kwargs["provider_cfg"].asr_provider == "openai"
    assert kwargs["provider_cfg"].llm_provider == "openai"
    assert kwargs["openai_asr_cfg"].asr_openai_model == "gpt-4o-mini-transcribe"
    assert kwargs["openai_asr_cfg"].openai_api_key == "cfg-key"
    assert kwargs["openai_asr_cfg"].openai_base_url == "https://asr.example/v1"
    assert kwargs["openai_llm_cfg"].llm_openai_model == "gpt-5-mini"


def test_main_passes_config_file_to_retranscribe(tmp_path: Path) -> None:
    segment_audio = tmp_path / "segment.mp3"
    segment_audio.write_bytes(b"mp3")
    log_path = tmp_path / "transcriptions.jsonl"
    log_path.write_text(
        (
            '{"timestamp":"2026-04-23T11:32:02-07:00",'
            f'"audio_file":"{segment_audio}",'
            '"duration_seconds":5.0,'
            '"raw_output":"hello"}\n'
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    with (
        patch("agent_cli.agents.diarize_live_session.write_ffconcat_manifest"),
        patch("agent_cli.agents.diarize_live_session.combine_segments"),
        patch("agent_cli.agents.diarize_live_session.save_metadata"),
        patch(
            "agent_cli.agents.diarize_live_session._saved_audio_duration_seconds", return_value=5.0
        ),
        patch("agent_cli.agents.diarize_live_session.run_retranscribe") as mock_run,
    ):
        exit_code = main(
            [
                "--date",
                "2026-04-23",
                "--start",
                "11:32",
                "--end",
                "12:29",
                "--transcription-log",
                str(log_path),
                "--output-dir",
                str(output_dir),
                "--retranscribe",
                "--hf-token",
                "token",
            ],
            config_file="custom.toml",
        )

    assert exit_code == 0
    assert mock_run.call_args.kwargs["config_file"] == "custom.toml"


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


def test_build_retranscribe_request_uses_speaker_hints() -> None:
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

    request = build_retranscribe_request(args, Path("meeting.wav"))

    assert request == {
        "audio_file": "meeting.wav",
        "diarize_format": "json",
        "min_speakers": 3,
        "max_speakers": 3,
        "align_words": True,
        "align_language": "en",
        "hf_token": True,
    }


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

    with (
        patch(
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
        ),
        patch(
            "agent_cli.agents.diarize_live_session._saved_audio_duration_seconds",
            side_effect=[2.0, 3.0],
        ),
    ):
        result = align_logged_segments_with_speakers(
            segments=segments,
            speaker_segments=speaker_segments,
        )

    assert [segment.speaker for segment in result] == ["SPEAKER_00", "SPEAKER_01"]
    assert result[0].text == "hello there general"
    assert result[1].text == "kenobi"


def test_align_logged_segments_with_speakers_uses_saved_audio_duration_offsets() -> None:
    segments = [
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:00-07:00"),
            audio_file=Path("one.mp3"),
            duration_seconds=2.0,
            raw_output="hello",
        ),
        LiveSegment(
            timestamp=datetime.fromisoformat("2026-04-23T11:32:05-07:00"),
            audio_file=Path("two.mp3"),
            duration_seconds=2.0,
            raw_output="general kenobi",
        ),
    ]
    speaker_segments = [
        DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.5),
        DiarizedSegment(speaker="SPEAKER_01", start=2.5, end=5.5),
    ]

    with (
        patch(
            "agent_cli.agents.diarize_live_session.align",
            side_effect=[
                [AlignedWord(word="hello", start=0.0, end=0.4)],
                [
                    AlignedWord(word="general", start=0.0, end=0.2),
                    AlignedWord(word="kenobi", start=0.2, end=0.4),
                ],
            ],
        ),
        patch(
            "agent_cli.agents.diarize_live_session._saved_audio_duration_seconds",
            side_effect=[2.6, 2.0],
        ),
    ):
        result = align_logged_segments_with_speakers(
            segments=segments,
            speaker_segments=speaker_segments,
        )

    assert [segment.speaker for segment in result] == ["SPEAKER_00", "SPEAKER_01"]
    assert result[0].text == "hello"
    assert result[1].text == "general kenobi"
