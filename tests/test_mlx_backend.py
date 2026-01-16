"""Tests for the MLX Whisper backend."""

from __future__ import annotations

import io
import wave
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.server.whisper.backends.base import BackendConfig
from agent_cli.server.whisper.backends.mlx import MLXWhisperBackend


def _make_wav_bytes(
    *,
    rate: int,
    channels: int,
    sampwidth: int,
    frames: int = 160,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\x00" * frames * channels * sampwidth)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_mlx_transcribe_converts_mismatched_wav() -> None:
    """Ensure MLX backend converts WAVs that do not match expected format."""
    config = BackendConfig(model_name="tiny")
    backend = MLXWhisperBackend(config)
    backend._executor = MagicMock()  # Simulate loaded state

    audio = _make_wav_bytes(rate=44100, channels=1, sampwidth=2)
    fake_result = {"text": "hello", "language": "en", "segments": []}

    async def mock_run_in_executor(_executor: Any, _func: Any, *_args: Any) -> dict[str, Any]:
        return fake_result

    with (
        patch(
            "agent_cli.server.whisper.backends.mlx._convert_audio_to_pcm",
            return_value=b"\x00\x00",
        ) as mock_convert,
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.run_in_executor = mock_run_in_executor
        result = await backend.transcribe(audio, source_filename="sample.wav")

    mock_convert.assert_called_once_with(audio, "sample.wav")
    assert result.text == "hello"


@pytest.mark.asyncio
async def test_mlx_transcribe_accepts_matching_wav() -> None:
    """Ensure MLX backend accepts 16kHz mono 16-bit WAV without conversion."""
    config = BackendConfig(model_name="tiny")
    backend = MLXWhisperBackend(config)
    backend._executor = MagicMock()  # Simulate loaded state

    audio = _make_wav_bytes(rate=16000, channels=1, sampwidth=2)
    fake_result = {"text": "hello", "language": "en", "segments": []}

    async def mock_run_in_executor(_executor: Any, _func: Any, *_args: Any) -> dict[str, Any]:
        return fake_result

    with (
        patch("agent_cli.server.whisper.backends.mlx._convert_audio_to_pcm") as mock_convert,
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.run_in_executor = mock_run_in_executor
        result = await backend.transcribe(audio, source_filename="sample.wav")

    mock_convert.assert_not_called()
    assert result.text == "hello"
