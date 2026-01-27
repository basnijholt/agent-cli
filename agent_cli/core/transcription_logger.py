"""Transcription logging utilities for automatic server-side logging."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TranscriptionLogger:
    """Handles automatic logging of transcription results with timestamps."""

    def __init__(self, log_file: Path | str | None = None) -> None:
        """Initialize the transcription logger.

        Args:
            log_file: Path to the log file. If None, uses default location.

        """
        if log_file is None:
            log_file = Path.home() / ".config" / "agent-cli" / "transcriptions.jsonl"
        elif isinstance(log_file, str):
            log_file = Path(log_file)

        self.log_file = log_file

        # Ensure the log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_transcription(
        self,
        *,
        raw: str,
        processed: str | None = None,
    ) -> None:
        """Log a transcription result.

        Args:
            raw: The raw transcript from ASR.
            processed: The processed transcript from LLM.

        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "raw": raw,
            "processed": processed,
        }

        # Write to log file as JSON Lines format
        try:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except OSError:
            # Use Python's logging module to log errors with the logger itself
            logger = logging.getLogger(__name__)
            logger.exception("Failed to write transcription log")


# Default logger instance
_default_logger: TranscriptionLogger | None = None


def get_default_logger() -> TranscriptionLogger:
    """Get the default transcription logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = TranscriptionLogger()
    return _default_logger
