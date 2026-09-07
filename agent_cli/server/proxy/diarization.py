"""Lazy, serialized speaker diarization for uploaded audio."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from agent_cli.core.diarization import (
    DiarizedSegment,
    SpeakerDiarizer,
    align_transcript_with_speakers,
    align_transcript_with_words,
)


class DiarizationService:
    """Keep one pipeline per server process and serialize inference in worker threads."""

    def __init__(self, hf_token: str, device: str) -> None:
        """Store model configuration without importing or loading pyannote."""
        self._hf_token = hf_token
        self._device = device
        self._diarizer: SpeakerDiarizer | None = None
        self._lock = Lock()

    def diarize(
        self,
        audio: bytes,
        filename: str,
        *,
        transcript: str | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        align_words: bool = False,
        align_language: str = "en",
    ) -> list[DiarizedSegment]:
        """Diarize an upload, optionally assigning transcript sentences to speakers.

        Args:
            audio: Original encoded audio file bytes.
            filename: Source filename, used only to preserve the audio extension.
            transcript: Optional transcript to align using estimated sentence timing.
            min_speakers: Minimum speaker count hint for this request.
            max_speakers: Maximum speaker count hint for this request.
            align_words: Use forced alignment instead of estimated sentence timing.
            align_language: Language of the forced alignment model.

        Returns:
            Speaker segments, with text when a transcript was supplied.

        """
        with self._lock:
            if self._diarizer is None:
                self._diarizer = SpeakerDiarizer(
                    hf_token=self._hf_token,
                    device=None if self._device == "auto" else self._device,
                )
            with TemporaryDirectory(prefix="agent-cli-diarize-") as directory:
                audio_path = Path(directory) / f"audio{Path(filename).suffix.lower()}"
                audio_path.write_bytes(audio)
                segments = self._diarizer.diarize(
                    audio_path,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
                if transcript:
                    if align_words:
                        segments = align_transcript_with_words(
                            transcript,
                            segments,
                            audio_path,
                            language=align_language,
                            device=self._diarizer.device,
                        )
                    else:
                        segments = align_transcript_with_speakers(transcript, segments)
                return segments


@lru_cache(maxsize=1)
def get_diarization_service(hf_token: str, device: str) -> DiarizationService:
    """Reuse the model for the server's configured token and device."""
    return DiarizationService(hf_token, device)
