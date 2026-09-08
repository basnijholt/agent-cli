"""Tests for the transformers Whisper backend helpers."""

from __future__ import annotations

import sys
import traceback
import wave
import weakref
from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agent_cli.server.whisper.backends import transformers as backend


class _FakeLoadedModel:
    """Minimal model double for exercising backend model selection."""

    def to(self, device: str) -> None:
        self.device = device

    def eval(self) -> None:
        self.is_eval = True


def test_download_model_resolves_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure download uses resolved model names and honors cache_dir."""
    calls: dict[str, object] = {}

    def snapshot_download(*, repo_id: str, cache_dir: str | None = None) -> None:
        calls["repo_id"] = repo_id
        calls["cache_dir"] = cache_dir

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )

    resolved = backend.download_model("tiny", cache_dir=tmp_path)
    assert resolved == "openai/whisper-tiny"
    assert calls["repo_id"] == "openai/whisper-tiny"
    assert calls["cache_dir"] == str(tmp_path)


def test_download_model_preserves_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure explicit repo IDs are passed through unchanged."""
    calls: dict[str, object] = {}

    def snapshot_download(*, repo_id: str, cache_dir: str | None = None) -> None:
        calls["repo_id"] = repo_id
        calls["cache_dir"] = cache_dir

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )

    resolved = backend.download_model("custom/whisper")
    assert resolved == "custom/whisper"
    assert calls["repo_id"] == "custom/whisper"
    assert calls["cache_dir"] is None


def test_load_qwen3_asr_uses_multimodal_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qwen3-ASR must not be loaded through the speech-seq2seq auto class."""
    calls: dict[str, object] = {}

    class AutoConfig:
        @staticmethod
        def from_pretrained(model_name: str, **kwargs: object) -> SimpleNamespace:
            calls["config"] = (model_name, kwargs)
            return SimpleNamespace(model_type="qwen3_asr")

    class AutoProcessor:
        @staticmethod
        def from_pretrained(model_name: str, **kwargs: object) -> object:
            calls["processor"] = (model_name, kwargs)
            return object()

    class AutoModelForMultimodalLM:
        @staticmethod
        def from_pretrained(model_name: str, **kwargs: object) -> _FakeLoadedModel:
            calls["multimodal_model"] = (model_name, kwargs)
            return _FakeLoadedModel()

    class AutoModelForSpeechSeq2Seq:
        @staticmethod
        def from_pretrained(_model_name: str, **_kwargs: object) -> object:
            raise AssertionError

    fake_torch = SimpleNamespace(
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        cuda=SimpleNamespace(is_available=lambda: False),
        float16="float16",
        float32="float32",
    )
    fake_transformers = SimpleNamespace(
        AutoConfig=AutoConfig,
        AutoModelForMultimodalLM=AutoModelForMultimodalLM,
        AutoModelForSpeechSeq2Seq=AutoModelForSpeechSeq2Seq,
        AutoProcessor=AutoProcessor,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setattr(backend, "_state", backend._SubprocessState())
    monkeypatch.setattr(backend, "set_process_title", lambda _title: None)

    device = backend._load_model_in_subprocess(
        "Qwen/Qwen3-ASR-1.7B-hf",
        "auto",
        None,
        False,
    )

    assert device == "cpu"
    assert calls["multimodal_model"][0] == "Qwen/Qwen3-ASR-1.7B-hf"  # type: ignore[index]
    assert backend._state.is_qwen3_asr is True


@pytest.mark.parametrize(
    ("model_name", "model_type", "expects_remote_code"),
    [
        ("openai/whisper-tiny", "whisper", False),
        ("CohereLabs/cohere-transcribe-03-2026", "cohere_asr", True),
    ],
)
def test_load_non_qwen_models_preserves_speech_seq2seq_path(
    monkeypatch: pytest.MonkeyPatch,
    model_name: str,
    model_type: str,
    expects_remote_code: bool,
) -> None:
    """Transformers 5 loading must preserve standard Whisper and Cohere models."""
    config = SimpleNamespace(model_type=model_type)
    config_kwargs_seen: dict[str, object] = {}
    model_kwargs_seen: dict[str, object] = {}

    class AutoConfig:
        @staticmethod
        def from_pretrained(name: str, **kwargs: object) -> SimpleNamespace:
            assert name == model_name
            config_kwargs_seen.update(kwargs)
            return config

    class AutoProcessor:
        @staticmethod
        def from_pretrained(name: str, **_kwargs: object) -> object:
            assert name == model_name
            return object()

    class AutoModelForSpeechSeq2Seq:
        @staticmethod
        def from_pretrained(name: str, **kwargs: object) -> _FakeLoadedModel:
            assert name == model_name
            model_kwargs_seen.update(kwargs)
            return _FakeLoadedModel()

    class AutoModelForMultimodalLM:
        @staticmethod
        def from_pretrained(_name: str, **_kwargs: object) -> object:
            raise AssertionError

    fake_torch = SimpleNamespace(
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        cuda=SimpleNamespace(is_available=lambda: False),
        float16="float16",
        float32="float32",
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoConfig=AutoConfig,
            AutoModelForMultimodalLM=AutoModelForMultimodalLM,
            AutoModelForSpeechSeq2Seq=AutoModelForSpeechSeq2Seq,
            AutoProcessor=AutoProcessor,
        ),
    )
    monkeypatch.setattr(backend, "_state", backend._SubprocessState())
    monkeypatch.setattr(backend, "set_process_title", lambda _title: None)

    backend._load_model_in_subprocess(model_name, "auto", None, False)

    assert config_kwargs_seen["trust_remote_code"] is expects_remote_code
    assert model_kwargs_seen["config"] is config
    assert model_kwargs_seen["dtype"] == "float32"
    assert model_kwargs_seen["trust_remote_code"] is expects_remote_code
    assert backend._state.is_cohere_asr is expects_remote_code
    assert backend._state.is_qwen3_asr is False


def test_transcribe_qwen3_asr_returns_parsed_transcription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qwen3-ASR should receive request hints and return its parsed output."""
    audio_input = object()

    class Tensor:
        def __init__(self, values: list[list[float | int]]) -> None:
            self.values = values
            self.shape = (len(values), len(values[0]))

        def to(self, *_args: object, **_kwargs: object) -> Tensor:
            return self

        def __getitem__(self, key: tuple[slice, slice]) -> Tensor:
            rows, columns = key
            return Tensor([row[columns] for row in self.values[rows]])

        def tolist(self) -> list[list[float | int]]:
            return self.values

    class Processor:
        def apply_transcription_request(
            self,
            *,
            audio: object,
            language: str | None,
            prompt: str | None,
        ) -> dict[str, Tensor]:
            if audio is not audio_input or language != "en" or prompt != "Vocabulary: Agent CLI":
                return {"input_ids": Tensor([[99]])}
            return {
                "input_ids": Tensor([[1, 2, 3]]),
                "input_features": Tensor([[0.25]]),
            }

        def decode(
            self,
            generated_ids: Tensor,
            *,
            return_format: str,
        ) -> list[dict[str, str]]:
            if generated_ids.tolist() != [[41, 42]] or return_format != "parsed":
                return [{"language": "Wrong", "transcription": "Wrong"}]
            return [{"language": "English", "transcription": "Agent CLI"}]

    class Model:
        generation_config = SimpleNamespace(eos_token_id=[42, 99])

        def generate(self, **inputs: Tensor | int | bool) -> Tensor:
            assert inputs["max_new_tokens"] == 2
            return Tensor([[1, 2, 3, 41, 42]])

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(inference_mode=nullcontext),
    )
    monkeypatch.setattr(
        backend,
        "_state",
        backend._SubprocessState(
            model=Model(),
            processor=Processor(),
            dtype="float32",
            device="cpu",
            is_qwen3_asr=True,
        ),
    )

    result = backend._transcribe_qwen3_asr(
        audio_array=audio_input,
        effective_language="en",
        task="transcribe",
        initial_prompt="Vocabulary: Agent CLI",
        duration=1.5,
        max_new_tokens=2,
    )

    assert result == {
        "text": "Agent CLI",
        "language": "English",
        "language_probability": 1.0,
        "duration": 1.5,
        "segments": [],
        "supports_segments": False,
    }


def test_transcribe_qwen3_asr_rejects_truncated_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qwen3-ASR must not return partial text when generation exhausts its limit."""

    class Tensor:
        def __init__(self, values: list[list[int]]) -> None:
            self.values = values
            self.shape = (len(values), len(values[0]))

        def to(self, *_args: object, **_kwargs: object) -> Tensor:
            return self

        def __getitem__(self, key: tuple[slice, slice]) -> Tensor:
            rows, columns = key
            return Tensor([row[columns] for row in self.values[rows]])

        def tolist(self) -> list[list[int]]:
            return self.values

    class Processor:
        def apply_transcription_request(self, **_kwargs: object) -> dict[str, Tensor]:
            return {"input_ids": Tensor([[1, 2, 3]])}

        def decode(self, *_args: object, **_kwargs: object) -> list[dict[str, str]]:
            raise AssertionError

    class Model:
        def generate(self, **_kwargs: object) -> Tensor:
            return Tensor([[1, 2, 3, 41, 42]])

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))
    monkeypatch.setattr(
        backend,
        "_state",
        backend._SubprocessState(
            model=Model(),
            processor=Processor(),
            dtype="float32",
            device="cpu",
            is_qwen3_asr=True,
        ),
    )

    with pytest.raises(backend.TranscriptionTruncatedError, match="max_new_tokens=2"):
        backend._transcribe_qwen3_asr(
            audio_array=object(),
            effective_language=None,
            task="transcribe",
            initial_prompt=None,
            duration=180.0,
            max_new_tokens=2,
        )


def test_transcribe_qwen3_asr_rejects_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Qwen3-ASR should reject translation before invoking its processor."""

    class Processor:
        def apply_transcription_request(self, **_kwargs: object) -> object:
            raise AssertionError

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(inference_mode=nullcontext),
    )
    monkeypatch.setattr(
        backend,
        "_state",
        backend._SubprocessState(processor=Processor()),
    )

    with pytest.raises(backend.UnsupportedRequestError, match="Translation is not supported"):
        backend._transcribe_qwen3_asr(
            audio_array=object(),
            effective_language=None,
            task="translate",
            initial_prompt=None,
            duration=1.0,
            max_new_tokens=4096,
        )


def test_transcribe_dispatches_qwen3_asr_to_native_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Qwen3-ASR should normalize non-16-bit WAVs before native processing."""
    wav_path = tmp_path / "24-bit.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(3)
        wav_file.setframerate(2)
        wav_file.writeframes(b"\x00\x00\x00")

    expected = {
        "text": "native Qwen path",
        "language": "English",
        "language_probability": 0.0,
        "duration": 0.5,
        "segments": [],
        "supports_segments": False,
    }
    qwen_audio = object()
    monkeypatch.setattr(
        backend,
        "_state",
        backend._SubprocessState(model=object(), processor=object(), is_qwen3_asr=True),
    )
    monkeypatch.setitem(
        sys.modules,
        "librosa",
        SimpleNamespace(
            load=lambda path, **kwargs: (
                qwen_audio
                if path == str(wav_path) and kwargs == {"sr": 16000, "mono": True}
                else object(),
                16000,
            ),
        ),
    )

    def transcribe_qwen3_asr(**kwargs: object) -> dict[str, object]:
        if (
            kwargs["audio_array"] is not qwen_audio
            or kwargs["duration"] != 0.5
            or kwargs["max_new_tokens"] != 2048
        ):
            return {**expected, "text": "wrong Qwen input"}
        return expected

    monkeypatch.setattr(backend, "_transcribe_qwen3_asr", transcribe_qwen3_asr)

    result = backend._transcribe_in_subprocess(
        {
            "wav_path": str(wav_path),
            "task": "transcribe",
            "initial_prompt": "Agent CLI",
            "max_new_tokens": 2048,
        },
    )

    assert result == expected


@pytest.mark.parametrize("device", ["cuda", "cuda:0", "cpu", "mps"])
@pytest.mark.parametrize(
    "failure", [None, "direct", "interrupt", "cause", "context", "group", "cycle"]
)
def test_transcription_releases_unused_cuda_buffers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: str,
    failure: str | None,
) -> None:
    """A completed or failed request must not retain CUDA's peak working set.

    PyTorch's caching allocator keeps freed tensor storage reserved until
    empty_cache(), which releases unused storage without unloading live tensors:
    https://docs.pytorch.org/docs/stable/notes/cuda.html#memory-management
    The small allocator double models that external boundary without a GPU.
    """

    class Buffer:
        def __init__(self, size: int) -> None:
            self.size = size

    class Allocator:
        def __init__(self) -> None:
            self.live: weakref.WeakSet[Buffer] = weakref.WeakSet()
            self.reserved = 0

        def allocate(self, size: int) -> Buffer:
            buffer = Buffer(size)
            self.live.add(buffer)
            self.reserved += size
            return buffer

        def empty_cache(self) -> None:
            if not device.startswith("cuda"):
                pytest.fail("CPU/MPS transcription must not initialize CUDA")
            self.reserved = sum(buffer.size for buffer in self.live)

    allocator = Allocator()
    weights = allocator.allocate(100)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=allocator))
    monkeypatch.setattr(
        backend,
        "_state",
        backend._SubprocessState(
            model=weights,
            processor=object(),
            device=device,
            is_qwen3_asr=True,
        ),
    )
    wav_path = tmp_path / "request.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00")
    monkeypatch.setattr(backend, "_load_qwen_audio", lambda _: object())

    def infer_inner() -> dict[str, object]:
        temporary = allocator.allocate(900)
        if failure:
            # Its traceback holds `temporary` until the worker clears frame locals.
            message = "inference failed"
            error_type = KeyboardInterrupt if failure == "interrupt" else RuntimeError
            raise error_type(message)
        return {"text": "transcribed", "working_set": temporary.size}

    def infer(**_kwargs: object) -> dict[str, object]:
        try:
            return infer_inner()
        except RuntimeError as exc:
            message = "inference failed"
            if failure == "cause":
                raise ValueError(message) from exc
            if failure == "context":
                raise ValueError(message) from None
            if failure == "group":
                raise ExceptionGroup(message, [exc]) from None
            if failure == "cycle":
                wrapped = ValueError(message)
                exc.__cause__ = wrapped
                raise wrapped from exc
            raise

    monkeypatch.setattr(backend, "_transcribe_qwen3_asr", infer)
    if failure:
        with pytest.raises(BaseException, match="inference failed") as error:
            backend._transcribe_in_subprocess({"wav_path": str(wav_path)})
        assert "infer" in [frame.name for frame in traceback.extract_tb(error.value.__traceback__)]
    else:
        assert backend._transcribe_in_subprocess({"wav_path": str(wav_path)}) == {
            "text": "transcribed",
            "working_set": 900,
        }

    assert allocator.reserved == (100 if device.startswith("cuda") else 1000)
    assert backend._state.model is weights
