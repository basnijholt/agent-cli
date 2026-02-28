"""Tests for core audio stream lifecycle helpers."""

from __future__ import annotations

import logging
import time
from typing import Any
from unittest.mock import MagicMock

from agent_cli.core import audio


class _FakeStream:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def stop(self, ignore_errors: bool = True) -> None:  # noqa: ARG002
        self.calls.append("stop")

    def abort(self, ignore_errors: bool = True) -> None:  # noqa: ARG002
        self.calls.append("abort")

    def close(self, ignore_errors: bool = True) -> None:  # noqa: ARG002
        self.calls.append("close")


def test_open_audio_stream_stops_and_closes() -> None:
    """open_audio_stream should start, then stop and close the stream."""
    stream = _FakeStream()
    config = MagicMock()
    config.to_stream.return_value = stream

    with audio.open_audio_stream(config):
        assert stream.calls == ["start"]

    assert stream.calls == ["start", "stop", "close"]


def test_open_audio_stream_uses_abort_when_stop_times_out(
    monkeypatch: Any,
) -> None:
    """open_audio_stream should fallback to abort when stop hangs."""
    stream = _FakeStream()
    config = MagicMock()
    config.to_stream.return_value = stream
    methods_called: list[str] = []

    def fake_call(
        _stream: object,
        method_name: str,
        *,
        timeout_seconds: float = audio._AUDIO_SHUTDOWN_TIMEOUT_SECONDS,
    ) -> bool:
        _ = timeout_seconds
        methods_called.append(method_name)
        return method_name != "stop"

    monkeypatch.setattr(audio, "_call_stream_method_with_timeout", fake_call)

    with audio.open_audio_stream(config):
        pass

    assert methods_called == ["stop", "abort", "close"]


def test_call_stream_method_with_timeout_timeout_logs_warning(
    caplog: Any,
) -> None:
    """Timeout path should log a warning and return False."""

    class _HangingStream:
        def stop(self, ignore_errors: bool = True) -> None:  # noqa: ARG002
            time.sleep(0.2)

    with caplog.at_level(logging.WARNING):
        result = audio._call_stream_method_with_timeout(
            _HangingStream(),
            "stop",
            timeout_seconds=0.01,
        )

    assert result is False
    assert "Timed out after" in caplog.text


def test_call_stream_method_with_timeout_exception_logs_warning(
    caplog: Any,
) -> None:
    """Exceptions from stream methods should be logged and reported as failure."""

    class _BrokenStream:
        def close(self, ignore_errors: bool = True) -> None:  # noqa: ARG002
            msg = "boom"
            raise RuntimeError(msg)

    with caplog.at_level(logging.WARNING):
        result = audio._call_stream_method_with_timeout(_BrokenStream(), "close")

    assert result is False
    assert "audio stream.close() failed" in caplog.text
