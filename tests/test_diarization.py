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
        result = align_transcript_with_speakers("Hello world.", [])
        assert result == []

    def test_empty_transcript(self):
        """Test with empty transcript."""
        segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]
        result = align_transcript_with_speakers("", segments)
        # Returns original segments when transcript is empty
        assert result == segments

    def test_single_segment(self):
        """Test alignment with a single segment."""
        segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=5.0)]
        result = align_transcript_with_speakers("Hello world.", segments)
        assert len(result) == 1
        assert result[0].text == "Hello world."
        assert result[0].speaker == "SPEAKER_00"

    def test_two_sentences_two_speakers(self):
        """Test that sentences are assigned to the correct speakers."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0),  # 2s
            DiarizedSegment(speaker="SPEAKER_01", start=2.0, end=4.0),  # 2s
        ]
        # Two sentences of roughly equal length
        transcript = "Hello, how are you? I am doing well."
        result = align_transcript_with_speakers(transcript, segments)
        assert len(result) == 2
        assert result[0].speaker == "SPEAKER_00"
        assert result[0].text == "Hello, how are you?"
        assert result[1].speaker == "SPEAKER_01"
        assert result[1].text == "I am doing well."

    def test_three_sentences_three_speakers(self):
        """Test sentences distribute across three speakers."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=1.0),  # 1s
            DiarizedSegment(speaker="SPEAKER_01", start=1.0, end=2.0),  # 1s
            DiarizedSegment(speaker="SPEAKER_02", start=2.0, end=3.0),  # 1s
        ]
        # Three sentences of roughly equal length
        transcript = "First sentence here. Second sentence here. Third sentence here."
        result = align_transcript_with_speakers(transcript, segments)
        assert len(result) == 3
        assert result[0].speaker == "SPEAKER_00"
        assert result[1].speaker == "SPEAKER_01"
        assert result[2].speaker == "SPEAKER_02"

    def test_consecutive_sentences_same_speaker_merged(self):
        """Test that consecutive sentences from same speaker are merged."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=3.0),  # 3s - one speaker
        ]
        transcript = "First sentence. Second sentence. Third sentence."
        result = align_transcript_with_speakers(transcript, segments)
        # All sentences should be merged into one segment
        assert len(result) == 1
        assert result[0].speaker == "SPEAKER_00"
        assert result[0].text == "First sentence. Second sentence. Third sentence."

    def test_zero_duration_fallback(self):
        """Test fallback when total duration is zero."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=0.0),
            DiarizedSegment(speaker="SPEAKER_01", start=0.0, end=0.0),
        ]
        transcript = "All text goes to first speaker."
        result = align_transcript_with_speakers(transcript, segments)
        # Zero duration fallback: all text to first speaker
        assert len(result) == 1
        assert result[0].speaker == "SPEAKER_00"
        assert result[0].text == transcript

    def test_single_sentence_no_punctuation(self):
        """Test that text without punctuation is treated as single sentence."""
        segments = [
            DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0),
            DiarizedSegment(speaker="SPEAKER_01", start=2.0, end=4.0),
        ]
        # No punctuation = single sentence = assigned to dominant speaker at start
        transcript = "hello world how are you"
        result = align_transcript_with_speakers(transcript, segments)
        assert len(result) == 1
        assert result[0].text == transcript


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
                token="test_token",  # noqa: S106
            )

    def test_diarizer_diarize(self, tmp_path: Path):
        """Test diarization with mocked pipeline."""
        import torch  # noqa: PLC0415

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

        # Mock DiarizeOutput (new API)
        mock_output = MagicMock()
        mock_output.speaker_diarization = mock_annotation

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = mock_output

        mock_pipeline_class = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline

        # Mock torchaudio.load
        mock_waveform = torch.zeros(1, 16000)
        mock_sample_rate = 16000

        with (
            patch("agent_cli.core.diarization._check_pyannote_installed"),
            patch.dict(
                "sys.modules",
                {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_class)},
            ),
            patch("torchaudio.load", return_value=(mock_waveform, mock_sample_rate)),
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
            # Pipeline should be called with audio dict, not file path
            mock_pipeline.assert_called_once()
            call_args = mock_pipeline.call_args[0][0]
            assert "waveform" in call_args
            assert "sample_rate" in call_args

    def test_diarizer_diarize_with_speaker_hints(self, tmp_path: Path):
        """Test diarization passes speaker hints to pipeline."""
        import torch  # noqa: PLC0415

        from agent_cli.core.diarization import SpeakerDiarizer  # noqa: PLC0415

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []

        # Mock DiarizeOutput (new API)
        mock_output = MagicMock()
        mock_output.speaker_diarization = mock_annotation

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = mock_output

        mock_pipeline_class = MagicMock()
        mock_pipeline_class.from_pretrained.return_value = mock_pipeline

        # Mock torchaudio.load
        mock_waveform = torch.zeros(1, 16000)
        mock_sample_rate = 16000

        with (
            patch("agent_cli.core.diarization._check_pyannote_installed"),
            patch.dict(
                "sys.modules",
                {"pyannote.audio": MagicMock(Pipeline=mock_pipeline_class)},
            ),
            patch("torchaudio.load", return_value=(mock_waveform, mock_sample_rate)),
        ):
            diarizer = SpeakerDiarizer(
                hf_token="test_token",  # noqa: S106
                min_speakers=2,
                max_speakers=4,
            )
            audio_file = tmp_path / "test.wav"
            audio_file.touch()

            diarizer.diarize(audio_file)

            # Check speaker hints were passed
            mock_pipeline.assert_called_once()
            call_kwargs = mock_pipeline.call_args[1]
            assert call_kwargs["min_speakers"] == 2
            assert call_kwargs["max_speakers"] == 4
