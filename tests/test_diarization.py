"""Tests for the speaker diarization module."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.core.diarization import (
    DiarizedSegment,
    align_transcript_with_speakers,
    format_diarized_output,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDiarizedSegment:
    """Tests for the DiarizedSegment dataclass."""

    def test_create_segment(self):
        """Test creating a diarized segment."""
        segment = DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.5, text="Hello")
        assert segment.speaker == "SPEAKER_00"
        assert segment.start == 0.0
        assert segment.end == 2.5
        assert segment.text == "Hello"

    def test_segment_default_text(self):
        """Test that text defaults to empty string."""
        segment = DiarizedSegment(speaker="SPEAKER_01", start=1.0, end=3.0)
        assert segment.text == ""


class TestAlignTranscriptWithSpeakers:
    """Tests for the align_transcript_with_speakers function."""

    def test_empty_segments(self):
        """Test with empty segment list."""
        result = align_transcript_with_speakers("Hello world", [])
        assert result == []

    def test_empty_transcript(self):
        """Test with empty transcript."""
        segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]
        result = align_transcript_with_speakers("", segments)
        assert len(result) == 1
        assert result[0].text == ""

    def test_single_segment(self):
        """Test alignment with a single segment."""
        segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=5.0)]
        result = align_transcript_with_speakers("Hello world", segments)
        assert len(result) == 1
        assert result[0].text == "Hello world"
        assert result[0].speaker == "SPEAKER_00"

    def test_multiple_segments_proportional(self):
        """Test word distribution based on segment duration."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0),  # 2s
            DiarizedSegment(speaker="SPEAKER_01", start=2.0, end=4.0),  # 2s
        ]
        result = align_transcript_with_speakers("one two three four", segments)
        assert len(result) == 2
        # With equal durations, words should be split roughly evenly
        # Last segment gets remaining words
        assert result[0].speaker == "SPEAKER_00"
        assert result[1].speaker == "SPEAKER_01"
        # Total words should equal original
        all_words = result[0].text.split() + result[1].text.split()
        assert all_words == ["one", "two", "three", "four"]

    def test_zero_duration_fallback(self):
        """Test fallback when total duration is zero."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=0.0),
            DiarizedSegment(speaker="SPEAKER_01", start=0.0, end=0.0),
        ]
        result = align_transcript_with_speakers("one two three four", segments)
        assert len(result) == 2
        # Words should be distributed evenly
        all_words = result[0].text.split() + result[1].text.split()
        assert all_words == ["one", "two", "three", "four"]


class TestFormatDiarizedOutput:
    """Tests for the format_diarized_output function."""

    def test_inline_format(self):
        """Test inline format output."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0, text="Hello"),
            DiarizedSegment(speaker="SPEAKER_01", start=2.0, end=4.0, text="Hi there"),
        ]
        result = format_diarized_output(segments, output_format="inline")
        expected = "[SPEAKER_00]: Hello\n[SPEAKER_01]: Hi there"
        assert result == expected

    def test_inline_skips_empty_text(self):
        """Test that inline format skips segments with empty text."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0, text="Hello"),
            DiarizedSegment(speaker="SPEAKER_01", start=2.0, end=4.0, text=""),
            DiarizedSegment(speaker="SPEAKER_00", start=4.0, end=6.0, text="Goodbye"),
        ]
        result = format_diarized_output(segments, output_format="inline")
        expected = "[SPEAKER_00]: Hello\n[SPEAKER_00]: Goodbye"
        assert result == expected

    def test_json_format(self):
        """Test JSON format output."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.5, text="Hello"),
            DiarizedSegment(speaker="SPEAKER_01", start=2.7, end=4.1, text="Hi there"),
        ]
        result = format_diarized_output(segments, output_format="json")
        parsed = json.loads(result)
        assert "segments" in parsed
        assert len(parsed["segments"]) == 2
        assert parsed["segments"][0]["speaker"] == "SPEAKER_00"
        assert parsed["segments"][0]["start"] == 0.0
        assert parsed["segments"][0]["end"] == 2.5
        assert parsed["segments"][0]["text"] == "Hello"
        assert parsed["segments"][1]["speaker"] == "SPEAKER_01"
        assert parsed["segments"][1]["start"] == 2.7
        assert parsed["segments"][1]["end"] == 4.1
        assert parsed["segments"][1]["text"] == "Hi there"

    def test_json_rounds_timestamps(self):
        """Test that JSON format rounds timestamps to 2 decimal places."""
        segments = [
            DiarizedSegment(
                speaker="SPEAKER_00",
                start=0.123456,
                end=2.987654,
                text="Hello",
            ),
        ]
        result = format_diarized_output(segments, output_format="json")
        parsed = json.loads(result)
        assert parsed["segments"][0]["start"] == 0.12
        assert parsed["segments"][0]["end"] == 2.99

    def test_empty_segments(self):
        """Test with empty segment list."""
        result_inline = format_diarized_output([], output_format="inline")
        result_json = format_diarized_output([], output_format="json")
        assert result_inline == ""
        parsed = json.loads(result_json)
        assert parsed["segments"] == []


class TestCheckPyannoteInstalled:
    """Tests for the pyannote installation check."""

    def test_check_raises_when_not_installed(self):
        """Test that ImportError is raised when pyannote is not installed."""
        from agent_cli.core.diarization import _check_pyannote_installed  # noqa: PLC0415

        with (
            patch.dict("sys.modules", {"pyannote.audio": None}),
            patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'pyannote'"),
            ),
            pytest.raises(ImportError) as exc_info,
        ):
            _check_pyannote_installed()
        assert "pyannote-audio is required" in str(exc_info.value)
        assert "pip install agent-cli[diarization]" in str(exc_info.value)


class TestSpeakerDiarizer:
    """Tests for the SpeakerDiarizer class."""

    def test_diarizer_init_without_pyannote(self):
        """Test that SpeakerDiarizer raises ImportError when pyannote not installed."""
        from agent_cli.core.diarization import SpeakerDiarizer  # noqa: PLC0415

        with (
            patch(
                "agent_cli.core.diarization._check_pyannote_installed",
                side_effect=ImportError("pyannote-audio is required"),
            ),
            pytest.raises(ImportError),
        ):
            SpeakerDiarizer(hf_token="test_token")  # noqa: S106

    def test_diarizer_init_with_mock_pyannote(self):
        """Test SpeakerDiarizer initialization with mocked pyannote."""
        from agent_cli.core.diarization import SpeakerDiarizer  # noqa: PLC0415

        mock_pipeline = MagicMock()
        mock_pipeline_class = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline

        with (
            patch(
                "agent_cli.core.diarization._check_pyannote_installed",
            ),
            patch.dict(
                "sys.modules",
                {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_class)},
            ),
        ):
            diarizer = SpeakerDiarizer(
                hf_token="test_token",  # noqa: S106
                min_speakers=2,
                max_speakers=4,
            )
            assert diarizer.min_speakers == 2
            assert diarizer.max_speakers == 4
            mock_pipeline_class.from_pretrained.assert_called_once_with(
                "pyannote/speaker-diarization-3.1",
                use_auth_token="test_token",  # noqa: S106
            )

    def test_diarizer_diarize(self, tmp_path: Path):
        """Test diarization with mocked pipeline."""
        from agent_cli.core.diarization import SpeakerDiarizer  # noqa: PLC0415

        # Create a mock diarization result
        mock_turn1 = MagicMock()
        mock_turn1.start = 0.0
        mock_turn1.end = 2.5
        mock_turn2 = MagicMock()
        mock_turn2.start = 2.5
        mock_turn2.end = 5.0

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = [
            (mock_turn1, None, "SPEAKER_00"),
            (mock_turn2, None, "SPEAKER_01"),
        ]

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = mock_annotation

        mock_pipeline_class = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline

        with (
            patch("agent_cli.core.diarization._check_pyannote_installed"),
            patch.dict(
                "sys.modules",
                {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_class)},
            ),
        ):
            diarizer = SpeakerDiarizer(hf_token="test_token")  # noqa: S106
            audio_file = tmp_path / "test.wav"
            audio_file.touch()

            segments = diarizer.diarize(audio_file)

            assert len(segments) == 2
            assert segments[0].speaker == "SPEAKER_00"
            assert segments[0].start == 0.0
            assert segments[0].end == 2.5
            assert segments[1].speaker == "SPEAKER_01"
            assert segments[1].start == 2.5
            assert segments[1].end == 5.0
            mock_pipeline.assert_called_once_with(str(audio_file))

    def test_diarizer_diarize_with_speaker_hints(self, tmp_path: Path):
        """Test diarization passes speaker hints to pipeline."""
        from agent_cli.core.diarization import SpeakerDiarizer  # noqa: PLC0415

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = mock_annotation

        mock_pipeline_class = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline

        with (
            patch("agent_cli.core.diarization._check_pyannote_installed"),
            patch.dict(
                "sys.modules",
                {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_class)},
            ),
        ):
            diarizer = SpeakerDiarizer(
                hf_token="test_token",  # noqa: S106
                min_speakers=2,
                max_speakers=4,
            )
            audio_file = tmp_path / "test.wav"
            audio_file.touch()

            diarizer.diarize(audio_file)

            mock_pipeline.assert_called_once_with(
                str(audio_file),
                min_speakers=2,
                max_speakers=4,
            )
