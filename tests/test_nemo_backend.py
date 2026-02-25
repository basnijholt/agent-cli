"""Tests for the NeMo Whisper backend helpers."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from agent_cli.server.cli import _is_parakeet_model
from agent_cli.server.whisper.backends import nemo as backend

if TYPE_CHECKING:
    from pathlib import Path


def _install_mock_nemo(
    monkeypatch: pytest.MonkeyPatch,
    calls: dict[str, object],
) -> None:
    """Install a minimal mock of nemo.collections.asr in sys.modules."""

    class _ASRModel:
        @staticmethod
        def from_pretrained(*, model_name: str) -> object:
            calls["model_name"] = model_name
            return object()

    nemo_module: Any = ModuleType("nemo")
    collections_module: Any = ModuleType("nemo.collections")
    asr_module: Any = ModuleType("nemo.collections.asr")
    asr_module.models = SimpleNamespace(ASRModel=_ASRModel)

    nemo_module.collections = collections_module
    collections_module.asr = asr_module

    monkeypatch.setitem(sys.modules, "nemo", nemo_module)
    monkeypatch.setitem(sys.modules, "nemo.collections", collections_module)
    monkeypatch.setitem(sys.modules, "nemo.collections.asr", asr_module)


def _install_mock_torch(monkeypatch: pytest.MonkeyPatch, *, cuda_available: bool) -> None:
    """Install a minimal mock torch module exposing cuda.is_available()."""

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return cuda_available

    torch_module: Any = ModuleType("torch")
    torch_module.cuda = _Cuda()
    monkeypatch.setitem(sys.modules, "torch", torch_module)


def test_download_model_resolves_parakeet_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure Parakeet shorthand resolves to the expected NeMo model ID."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("parakeet-tdt-0.6b-v2")
    assert resolved == "nvidia/parakeet-tdt-0.6b-v2"
    assert calls["model_name"] == "nvidia/parakeet-tdt-0.6b-v2"


def test_download_model_preserves_repo_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure explicit model IDs are passed through unchanged."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("nvidia/parakeet-tdt-0.6b-v2")
    assert resolved == "nvidia/parakeet-tdt-0.6b-v2"
    assert calls["model_name"] == "nvidia/parakeet-tdt-0.6b-v2"


def test_extract_text_supports_str_dict_and_object() -> None:
    """Ensure transcript extraction supports the NeMo shapes we accept."""
    assert backend._extract_text("  hello  ") == "hello"
    assert backend._extract_text({"text": "  world  "}) == "world"
    assert backend._extract_text(SimpleNamespace(text="  nemo  ")) == "nemo"


def test_extract_segments_uses_segment_timestamps_by_default() -> None:
    """Ensure segment timestamps are mapped to OpenAI-compatible segment objects."""
    hypothesis = SimpleNamespace(
        timestamp={
            "segment": [
                {
                    "segment": "  Hello world  ",
                    "start": 0.16,
                    "end": 1.28,
                },
            ],
        },
    )

    assert backend._extract_segments(hypothesis, word_timestamps=False) == [
        {
            "id": 0,
            "start": 0.16,
            "end": 1.28,
            "text": "Hello world",
            "tokens": [],
            "avg_logprob": 0.0,
            "no_speech_prob": 0.0,
        },
    ]


def test_extract_segments_uses_word_timestamps_when_requested() -> None:
    """Ensure word timestamps are preferred when explicitly requested."""
    hypothesis = SimpleNamespace(
        timestamp={
            "word": [
                {
                    "word": "  hello  ",
                    "start": 0.1,
                    "end": 0.5,
                },
                {
                    "word": "world",
                    "start": 0.5,
                    "end": 1.0,
                },
            ],
        },
    )

    assert backend._extract_segments(hypothesis, word_timestamps=True) == [
        {
            "id": 0,
            "start": 0.1,
            "end": 0.5,
            "text": "hello",
            "tokens": [],
            "avg_logprob": 0.0,
            "no_speech_prob": 0.0,
        },
        {
            "id": 1,
            "start": 0.5,
            "end": 1.0,
            "text": "world",
            "tokens": [],
            "avg_logprob": 0.0,
            "no_speech_prob": 0.0,
        },
    ]


def test_extract_segments_returns_empty_when_timestamp_shape_is_unexpected() -> None:
    """Ensure segment extraction gracefully handles unsupported timestamp shapes."""
    assert backend._extract_segments(SimpleNamespace(timestamp=None), word_timestamps=False) == []
    assert backend._extract_segments({"timestamp": []}, word_timestamps=False) == []


def test_resolve_device_auto_uses_cuda_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure auto device selection prefers CUDA when available."""
    _install_mock_torch(monkeypatch, cuda_available=True)
    assert backend._resolve_device("auto") == "cuda"


def test_resolve_device_auto_falls_back_to_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure auto device selection falls back to CPU."""
    _install_mock_torch(monkeypatch, cuda_available=False)
    assert backend._resolve_device("auto") == "cpu"


def test_resolve_device_explicit_cuda_requires_available_cuda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure explicit CUDA requests fail fast when CUDA is unavailable."""
    _install_mock_torch(monkeypatch, cuda_available=False)

    with pytest.raises(RuntimeError, match="CUDA device requested"):
        backend._resolve_device("cuda:0")


def test_resolve_device_preserves_explicit_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure explicit non-auto device values are preserved."""
    _install_mock_torch(monkeypatch, cuda_available=False)
    assert backend._resolve_device("cpu") == "cpu"


def test_audio_duration_seconds_returns_zero_for_non_wav(tmp_path: Path) -> None:
    """Ensure non-WAV uploads do not raise duration parsing errors."""
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"ID3" + b"\x00" * 8)
    assert backend._audio_duration_seconds(str(audio_path)) == 0.0


def test_is_parakeet_model_matches_only_supported_identifiers() -> None:
    """Ensure Parakeet detection aligns with NeMo model-name resolution."""
    assert _is_parakeet_model("parakeet-tdt-0.6b-v2")
    assert _is_parakeet_model("nvidia/parakeet-tdt-0.6b-v2")
    assert _is_parakeet_model("nvidia/parakeet-custom")
    assert not _is_parakeet_model("Parakeet-TDT-0.6b-v2")
    assert not _is_parakeet_model("large-v3")
