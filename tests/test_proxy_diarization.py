"""HTTP diarization contracts, with only model inference and remote ASR replaced."""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003
from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_cli.core.diarization import DiarizedSegment, SpeakerDiarizer
from agent_cli.server.proxy import api
from agent_cli.server.proxy.diarization import get_diarization_service

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    get_diarization_service.cache_clear()
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setenv("ASR_PROVIDER", "openai")
    monkeypatch.setattr(api, "get_default_logger", MagicMock())
    monkeypatch.setattr(api, "_process_transcript_cleanup", AsyncMock(return_value=None))
    monkeypatch.setattr(
        api,
        "_transcribe_with_provider",
        AsyncMock(return_value="Hello there. Welcome back."),
    )
    yield TestClient(api.app)
    get_diarization_service.cache_clear()


@pytest.fixture
def inference(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Keep real request handling, temporary files and text alignment."""
    paths: list[Path] = []

    def initialize(self: SpeakerDiarizer, **kwargs: object) -> None:  # noqa: ARG001
        self.device = "cpu"

    def diarize(self: SpeakerDiarizer, audio_path: Path, **kwargs: object) -> list[DiarizedSegment]:  # noqa: ARG001
        assert audio_path.read_bytes() == b"original audio"
        paths.append(audio_path)
        return [
            DiarizedSegment("SPEAKER_00", 0.0, 2.0),
            DiarizedSegment("SPEAKER_01", 2.0, 4.0),
        ]

    monkeypatch.setattr(SpeakerDiarizer, "__init__", initialize)
    monkeypatch.setattr(SpeakerDiarizer, "diarize", diarize)
    return paths


def test_diarize_returns_timestamps_and_removes_upload(client: TestClient, inference: list[Path]):
    response = client.post("/diarize", files={"audio": ("recording.wav", b"original audio")})
    assert response.status_code == 200
    assert response.json() == {
        "segments": [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 2.0, "text": ""},
            {"speaker": "SPEAKER_01", "start": 2.0, "end": 4.0, "text": ""},
        ],
    }
    assert len(inference) == 1
    assert not inference[0].exists()


def test_transcribe_returns_speaker_text(client: TestClient, inference: list[Path]):
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["raw_transcript"] == "Hello there. Welcome back."
    assert [s["speaker"] for s in data["segments"]] == ["SPEAKER_00", "SPEAKER_01"]
    assert [s["text"] for s in data["segments"]] == ["Hello there.", "Welcome back."]
    assert not inference[0].exists()


def test_diarization_uses_original_upload_for_wyoming(
    client: TestClient,
    inference: list[Path],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ASR_PROVIDER", "wyoming")
    monkeypatch.setattr(api, "_convert_audio_for_local_asr", lambda *_: b"raw PCM")
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.mp3", b"original audio")},
        data={"diarize": "true", "cleanup": "false"},
    )
    assert response.json()["success"] is True
    assert len(inference) == 1
    assert inference[0].suffix == ".mp3"


@pytest.mark.parametrize("route", ["/diarize", "/transcribe"])
def test_diarization_requires_server_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
):
    monkeypatch.delenv("HF_TOKEN")
    monkeypatch.setattr(api.config, "load_config", dict)
    response = client.post(
        route,
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false"},
    )
    assert response.status_code == 503
    assert "HF_TOKEN" in response.json()["detail"]


@pytest.mark.parametrize("route", ["/diarize", "/transcribe"])
@pytest.mark.parametrize(
    "hints", [{"min_speakers": "0"}, {"min_speakers": "3", "max_speakers": "2"}]
)
def test_invalid_speaker_hints(client: TestClient, route: str, hints: dict[str, str]):
    response = client.post(
        route,
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false", **hints},
    )
    assert response.status_code == 422


def test_diarization_rejects_cleanup(client: TestClient):
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "true"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("route", ["/diarize", "/transcribe"])
def test_empty_diarization_upload(client: TestClient, route: str):
    response = client.post(
        route,
        files={"audio": ("recording.wav", b"")},
        data={"diarize": "true", "cleanup": "false"},
    )
    assert response.status_code == 400


def test_diarization_failure_is_not_success(
    client: TestClient,
    inference: list[Path],
    monkeypatch: pytest.MonkeyPatch,
):
    def fail(self: SpeakerDiarizer, audio_path: Path, **kwargs: object) -> list[DiarizedSegment]:  # noqa: ARG001
        inference.append(audio_path)
        msg = "model failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(SpeakerDiarizer, "diarize", fail)
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false"},
    )
    assert response.status_code == 500
    assert not inference[0].exists()


def test_request_speaker_hints_do_not_leak(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Per-request hints must not overwrite constructor defaults on a cached pipeline."""
    diarizer = SpeakerDiarizer.__new__(SpeakerDiarizer)
    diarizer.min_speakers = None
    diarizer.max_speakers = None
    diarizer.pipeline = MagicMock()
    diarizer.pipeline.return_value.speaker_diarization.itertracks.return_value = []
    monkeypatch.setattr(
        "agent_cli.core.diarization._load_audio_for_diarization",
        lambda _: (object(), 16000),
    )
    diarizer.diarize(tmp_path / "recording.wav", min_speakers=2, max_speakers=3)
    diarizer.diarize(tmp_path / "recording.wav")
    assert diarizer.pipeline.call_args_list[0].kwargs == {"min_speakers": 2, "max_speakers": 3}
    assert diarizer.pipeline.call_args_list[1].kwargs == {}


def test_word_alignment_uses_actual_timing(
    client: TestClient,
    inference: list[Path],
    monkeypatch: pytest.MonkeyPatch,
):
    """Moving word alignment onto the sentence heuristic mislabels 'there'."""
    from agent_cli.core.alignment import AlignedWord  # noqa: PLC0415

    monkeypatch.setattr(
        "agent_cli.core.diarization.align",
        lambda *_, **__: [
            AlignedWord("Hello", 0.0, 1.0),
            AlignedWord("there.", 2.0, 2.5),
            AlignedWord("Welcome", 2.5, 3.0),
            AlignedWord("back.", 3.0, 4.0),
        ],
    )
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false", "align_words": "true"},
    )
    assert response.json()["segments"] == [
        {"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0, "text": "Hello"},
        {"speaker": "SPEAKER_01", "start": 2.0, "end": 4.0, "text": "there. Welcome back."},
    ]
    assert not inference[0].exists()


def test_unsupported_alignment_language(client: TestClient):
    response = client.post(
        "/transcribe",
        files={"audio": ("recording.wav", b"original audio")},
        data={"diarize": "true", "cleanup": "false", "align_words": "true", "align_language": "xx"},
    )
    assert response.status_code == 422


def test_diarize_does_not_require_valid_asr_config(
    client: TestClient,
    inference: list[Path],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ASR_WYOMING_PORT", "not-a-port")
    response = client.post("/diarize", files={"audio": ("recording.wav", b"original audio")})
    assert response.status_code == 200
    assert len(inference) == 1


@pytest.mark.asyncio
async def test_concurrent_requests_reuse_model_and_keep_health_responsive(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    """Blocking inference must neither freeze health checks nor overlap on one pipeline."""
    entered = Event()
    release = Event()
    loaded: list[str] = []
    active = 0
    peak_active = 0

    def initialize(self: SpeakerDiarizer, **kwargs: object) -> None:  # noqa: ARG001
        loaded.append("loaded")
        self.device = "cpu"

    def diarize(self: SpeakerDiarizer, audio_path: Path, **kwargs: object) -> list[DiarizedSegment]:  # noqa: ARG001
        nonlocal active, peak_active
        active += 1
        peak_active = max(active, peak_active)
        entered.set()
        try:
            assert release.wait(2)
            return [DiarizedSegment("SPEAKER_00", 0, 1)]
        finally:
            active -= 1

    monkeypatch.setattr(SpeakerDiarizer, "__init__", initialize)
    monkeypatch.setattr(SpeakerDiarizer, "diarize", diarize)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://test",
    ) as session:
        first = asyncio.create_task(
            session.post(
                "/diarize",
                files={"audio": ("one.wav", b"audio")},
            )
        )
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            second = asyncio.create_task(
                session.post(
                    "/diarize",
                    files={"audio": ("two.wav", b"audio")},
                )
            )
            health = await asyncio.wait_for(session.get("/health"), timeout=1)
            assert health.status_code == 200
            await asyncio.sleep(0.05)
        finally:
            release.set()
            responses = await asyncio.gather(first, *([second] if second else []))
    assert len(responses) == 2
    assert all(response.status_code == 200 for response in responses)
    assert loaded == ["loaded"]
    assert peak_active == 1


def test_model_load_failure_can_retry(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    attempts = 0

    def initialize(self: SpeakerDiarizer, **kwargs: object) -> None:  # noqa: ARG001
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            msg = "Dependencies unavailable"
            raise ImportError(msg)
        self.device = "cpu"

    monkeypatch.setattr(SpeakerDiarizer, "__init__", initialize)
    monkeypatch.setattr(SpeakerDiarizer, "diarize", lambda *_, **__: [])
    first = client.post("/diarize", files={"audio": ("recording.wav", b"audio")})
    second = client.post("/diarize", files={"audio": ("recording.wav", b"audio")})
    assert first.status_code == 503
    assert second.status_code == 200
    assert second.json() == {"segments": []}
