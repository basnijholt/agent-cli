"""Tests for the NeMo Whisper backend helpers."""

from __future__ import annotations

import io
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from agent_cli.server.cli import _is_parakeet_model
from agent_cli.server.whisper.backends import nemo as backend
from agent_cli.server.whisper.backends.base import BackendConfig, InvalidAudioError

if TYPE_CHECKING:
    from pathlib import Path


def _install_mock_nemo(
    monkeypatch: pytest.MonkeyPatch,
    calls: dict[str, object],
    *,
    model: object | None = None,
) -> None:
    """Install a minimal mock of nemo.collections.asr in sys.modules."""

    class _ASRModel:
        @staticmethod
        def from_pretrained(*, model_name: str) -> object:
            calls["model_name"] = model_name
            return model if model is not None else object()

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


def _create_test_wav() -> bytes:
    """Create a tiny valid WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("alias", "resolved"),
    [
        ("parakeet-tdt-0.6b-v2", "nvidia/parakeet-tdt-0.6b-v2"),
        ("parakeet-tdt-0.6b-v3", "nvidia/parakeet-tdt-0.6b-v3"),
        ("parakeet-unified-en-0.6b", "nvidia/parakeet-unified-en-0.6b"),
        ("parakeet-tdt-1.1b", "nvidia/parakeet-tdt-1.1b"),
        ("parakeet-ctc-0.6b", "nvidia/parakeet-ctc-0.6b"),
        ("parakeet-ctc-1.1b", "nvidia/parakeet-ctc-1.1b"),
        ("parakeet-rnnt-0.6b", "nvidia/parakeet-rnnt-0.6b"),
        ("parakeet-rnnt-1.1b", "nvidia/parakeet-rnnt-1.1b"),
        ("parakeet-tdt_ctc-110m", "nvidia/parakeet-tdt_ctc-110m"),
    ],
)
def test_download_model_resolves_parakeet_aliases(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    resolved: str,
) -> None:
    """Ensure Parakeet shorthand resolves to the expected NeMo model ID."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    assert backend.download_model(alias) == resolved
    assert calls["model_name"] == resolved


def test_download_model_preserves_repo_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure non-Parakeet model IDs are passed through unchanged."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("Org/Custom-ASR")
    assert resolved == "Org/Custom-ASR"
    assert calls["model_name"] == "Org/Custom-ASR"


def test_download_model_normalizes_parakeet_repo_id_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure Parakeet repo IDs are normalized to a known canonical form."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("NVIDIA/Parakeet-TDT-0.6b-v2")
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


def test_load_model_fills_missing_validation_ds_for_unified_parakeet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NeMo transcribe expects validation_ds to be a mapping, not None."""

    class _Model:
        def __init__(self) -> None:
            self.cfg = SimpleNamespace(validation_ds=None)

        def to(self, device: str) -> _Model:
            assert device == "cpu"
            return self

        def eval(self) -> None:
            return None

    calls: dict[str, object] = {}
    model = _Model()
    _install_mock_torch(monkeypatch, cuda_available=False)
    _install_mock_nemo(monkeypatch, calls, model=model)
    monkeypatch.setattr(backend._state, "model", None)
    monkeypatch.setattr(backend._state, "device", None)

    assert backend._load_model_in_subprocess("nvidia/parakeet-unified-en-0.6b", "cpu") == "cpu"

    assert calls["model_name"] == "nvidia/parakeet-unified-en-0.6b"
    assert model.cfg.validation_ds == {}
    assert backend._state.model is model


def test_audio_duration_seconds_returns_zero_for_non_wav(tmp_path: Path) -> None:
    """Ensure non-WAV uploads do not raise duration parsing errors."""
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"ID3" + b"\x00" * 8)
    assert backend._audio_duration_seconds(str(audio_path)) == 0.0


def test_prepare_audio_for_nemo_keeps_valid_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid WAV uploads should not require FFmpeg conversion."""
    audio = _create_test_wav()
    monkeypatch.setattr(
        backend,
        "convert_audio_to_wav_format",
        lambda *_args, **_kwargs: pytest.fail("unexpected conversion"),
    )

    assert backend._prepare_audio_for_nemo(audio, "sample.wav") == audio


def test_prepare_audio_for_nemo_converts_non_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-WAV uploads should be converted to a WAV container before NeMo sees them."""
    converted = _create_test_wav()
    calls: dict[str, object] = {}

    def fake_convert(audio: bytes, source_filename: str) -> bytes:
        calls["audio"] = audio
        calls["source_filename"] = source_filename
        return converted

    monkeypatch.setattr(backend, "convert_audio_to_wav_format", fake_convert)

    assert backend._prepare_audio_for_nemo(b"ID3", "sample.mp3") == converted
    assert calls == {"audio": b"ID3", "source_filename": "sample.mp3"}


def test_prepare_audio_for_nemo_raises_invalid_audio_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversion failures should become API-visible invalid-audio errors."""

    def fake_convert(audio: bytes, source_filename: str) -> bytes:  # noqa: ARG001
        msg = "ffmpeg failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(backend, "convert_audio_to_wav_format", fake_convert)

    with pytest.raises(InvalidAudioError, match="Unsupported audio format for NeMo"):
        backend._prepare_audio_for_nemo(b"not audio", "sample.mp3")


def test_build_transcribe_kwargs_omits_language_for_plain_asr_models() -> None:
    """Plain NeMo ASR transcribe signatures should not receive unsupported language args."""

    def transcribe(audio: list[str], *, timestamps: bool) -> None:  # noqa: ARG001
        return None

    assert backend._build_transcribe_kwargs(
        transcribe,
        language="de",
        word_timestamps=True,
    ) == {"timestamps": True}


def test_build_transcribe_kwargs_requests_segment_timestamps_by_default() -> None:
    """NeMo should request segment timestamps even when word timestamps are off."""

    def transcribe(audio: list[str], *, timestamps: bool) -> None:  # noqa: ARG001
        return None

    assert backend._build_transcribe_kwargs(
        transcribe,
        language=None,
        word_timestamps=False,
    ) == {"timestamps": True}


def test_transcribe_in_subprocess_requests_and_extracts_segment_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SRT/VTT/verbose_json need segment timestamps with word_timestamps=False."""
    calls: dict[str, object] = {}

    class _Model:
        @staticmethod
        def transcribe(audio: list[str], **kwargs: object) -> list[object]:  # noqa: ARG004
            calls["kwargs"] = kwargs
            return [
                SimpleNamespace(
                    text="hello",
                    timestamp={
                        "segment": [{"segment": "hello", "start": 0.0, "end": 0.01}],
                    },
                ),
            ]

    monkeypatch.setattr(backend._state, "model", _Model())

    result = backend._transcribe_in_subprocess(
        _create_test_wav(),
        {"language": None, "word_timestamps": False},
    )

    assert calls["kwargs"] == {"timestamps": True}
    assert result["segments"] == [
        {
            "id": 0,
            "start": 0.0,
            "end": 0.01,
            "text": "hello",
            "tokens": [],
            "avg_logprob": 0.0,
            "no_speech_prob": 0.0,
        },
    ]


def test_build_transcribe_kwargs_passes_target_lang_for_prompt_models() -> None:
    """Prompt-conditioned Parakeet signatures should receive target_lang."""

    def transcribe(audio: list[str], *, timestamps: bool, **prompt: str) -> None:  # noqa: ARG001
        return None

    assert backend._build_transcribe_kwargs(
        transcribe,
        language="de-DE",
        word_timestamps=True,
    ) == {"timestamps": True, "target_lang": "de-DE"}


@pytest.mark.asyncio
async def test_unload_waits_for_subprocess_shutdown() -> None:
    """NeMo unload should wait for subprocess shutdown before reporting unloaded."""

    class _Executor:
        def __init__(self) -> None:
            self.shutdown_args: tuple[bool, bool] | None = None

        def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
            self.shutdown_args = (wait, cancel_futures)

    executor = _Executor()
    nemo_backend = backend.NemoWhisperBackend(
        BackendConfig(model_name="parakeet-tdt-0.6b-v3"),
    )
    nemo_backend._executor = executor  # type: ignore[assignment]  # Test double.

    await nemo_backend.unload()

    assert executor.shutdown_args == (True, True)
    assert not nemo_backend.is_loaded


@pytest.mark.asyncio
async def test_transcribe_recovers_from_broken_process_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NeMo backend should clear and reload a broken subprocess pool once."""
    nemo_backend = backend.NemoWhisperBackend(
        BackendConfig(model_name="parakeet-tdt-0.6b-v3"),
    )
    nemo_backend._executor = ThreadPoolExecutor(max_workers=1)  # type: ignore[assignment]
    calls = {"transcribe": 0, "load": 0}

    def transcribe_once_then_succeed(
        audio: bytes,  # noqa: ARG001
        kwargs: dict[str, Any],  # noqa: ARG001
    ) -> dict[str, Any]:
        calls["transcribe"] += 1
        if calls["transcribe"] == 1:
            raise BrokenProcessPool
        return {
            "text": "ok",
            "language": "en",
            "language_probability": 0.95,
            "duration": 1.0,
            "segments": [],
        }

    async def fake_load() -> float:
        calls["load"] += 1
        nemo_backend._executor = ThreadPoolExecutor(max_workers=1)  # type: ignore[assignment]
        return 0.0

    monkeypatch.setattr(backend, "_transcribe_in_subprocess", transcribe_once_then_succeed)
    monkeypatch.setattr(nemo_backend, "load", fake_load)

    result = await nemo_backend.transcribe(_create_test_wav())

    await nemo_backend.unload()
    assert result.text == "ok"
    assert calls == {"transcribe": 2, "load": 1}


def test_is_parakeet_model_matches_only_supported_identifiers() -> None:
    """Ensure Parakeet detection aligns with NeMo model-name resolution."""
    assert _is_parakeet_model("parakeet-tdt-0.6b-v2")
    assert _is_parakeet_model("parakeet-tdt-0.6b-v3")
    assert _is_parakeet_model("parakeet-unified-en-0.6b")
    assert _is_parakeet_model("parakeet-tdt-1.1b")
    assert _is_parakeet_model("parakeet-ctc-0.6b")
    assert _is_parakeet_model("nvidia/parakeet-tdt-0.6b-v2")
    assert _is_parakeet_model("nvidia/parakeet-custom")
    assert _is_parakeet_model("Parakeet-TDT-0.6b-v2")
    assert _is_parakeet_model(" NVIDIA/Parakeet-TDT-0.6b-v2 ")
    assert not _is_parakeet_model("large-v3")
