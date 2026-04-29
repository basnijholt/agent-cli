"""Tests for speaker profile CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import agent_cli.config as config_module
from agent_cli.agents import speakers as speakers_module
from agent_cli.cli import app
from agent_cli.core.diarization import DiarizedSegment
from agent_cli.core.speaker_identity import DEFAULT_SPEAKER_EMBEDDING_MODEL

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def _write_profile_store(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": DEFAULT_SPEAKER_EMBEDDING_MODEL,
                "next_unknown_id": 2,
                "profiles": [
                    {
                        "id": "UNKNOWN_001",
                        "name": None,
                        "anonymous": True,
                        "embeddings": [[0.0, 1.0]],
                        "created_at": "2026-04-24T16:00:00+00:00",
                        "updated_at": "2026-04-24T16:00:00+00:00",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )


def _write_duplicate_profile_store(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": DEFAULT_SPEAKER_EMBEDDING_MODEL,
                "next_unknown_id": 3,
                "profiles": [
                    {
                        "id": "john",
                        "name": "John",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                        "created_at": "2026-04-24T16:00:00+00:00",
                        "updated_at": "2026-04-24T16:00:00+00:00",
                    },
                    {
                        "id": "UNKNOWN_002",
                        "name": None,
                        "anonymous": True,
                        "embeddings": [[0.99, 0.01]],
                        "created_at": "2026-04-24T17:00:00+00:00",
                        "updated_at": "2026-04-24T17:00:00+00:00",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )


def test_speakers_list_outputs_profiles(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_profile_store(profiles_file)

    result = runner.invoke(
        app,
        ["speakers", "list", "--speaker-profiles-file", str(profiles_file)],
    )

    assert result.exit_code == 0
    assert "UNKNOWN_001" in result.stdout
    assert "unknown" in result.stdout


def test_speakers_list_json_outputs_profile_metadata(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_profile_store(profiles_file)

    result = runner.invoke(
        app,
        ["speakers", "list", "--speaker-profiles-file", str(profiles_file), "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["speaker_profiles_file"] == str(profiles_file)
    assert data["profiles"][0]["id"] == "UNKNOWN_001"
    assert data["profiles"][0]["embedding_count"] == 1
    assert "embeddings" not in data["profiles"][0]


def test_speakers_list_uses_configured_profile_file(tmp_path: Path) -> None:
    default_profiles_file = tmp_path / "default-speaker-profiles.json"
    profiles_file = tmp_path / "configured-speaker-profiles.json"
    config_file = tmp_path / "config.toml"
    _write_profile_store(profiles_file)
    config_file.write_text(
        f"""
[defaults]
speaker-profiles-file = "{default_profiles_file}"

[speakers]
speaker-profiles-file = "{profiles_file}"
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["speakers", "list", "--config", str(config_file), "--json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["speaker_profiles_file"] == str(profiles_file)
    assert data["profiles"][0]["id"] == "UNKNOWN_001"


def test_speakers_list_auto_loads_configured_profile_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    profiles_file = tmp_path / "configured-speaker-profiles.json"
    config_file = tmp_path / "config.toml"
    _write_profile_store(profiles_file)
    config_file.write_text(
        f"""
[defaults]
speaker-profiles-file = "{profiles_file}"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_PATHS", [config_file])

    result = runner.invoke(app, ["speakers", "list", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["speaker_profiles_file"] == str(profiles_file)
    assert data["profiles"][0]["id"] == "UNKNOWN_001"


def test_speakers_rename_updates_profile_name(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "rename",
            "UNKNOWN_001",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
        ],
    )

    assert result.exit_code == 0
    assert "John" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    profile = store["profiles"][0]
    assert profile["id"] == "UNKNOWN_001"
    assert profile["name"] == "John"
    assert profile["anonymous"] is False
    assert profile["embeddings"] == [[0.0, 1.0]]


def test_speakers_rename_json_outputs_profile_metadata(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "rename",
            "UNKNOWN_001",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["profile"]["id"] == "UNKNOWN_001"
    assert data["profile"]["name"] == "John"
    assert data["profile"]["anonymous"] is False


def test_speakers_rename_missing_profile_exits_nonzero(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "rename",
            "UNKNOWN_999",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
        ],
    )

    assert result.exit_code == 1
    assert "No speaker profile matching" in result.stdout


def test_speakers_rename_duplicate_name_suggests_merge(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_duplicate_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "rename",
            "UNKNOWN_002",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
        ],
    )

    assert result.exit_code == 1
    assert "Another speaker profile already uses 'John'." in result.stdout
    assert "speakers merge UNKNOWN_002 John" in result.stdout


def test_speakers_merge_moves_embeddings_and_removes_duplicate(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_duplicate_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "merge",
            "UNKNOWN_002",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
        ],
    )

    assert result.exit_code == 0
    assert "UNKNOWN_002" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert [profile["id"] for profile in store["profiles"]] == ["john"]
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]


def test_speakers_merge_json_outputs_target_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_duplicate_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "merge",
            "UNKNOWN_002",
            "John",
            "--speaker-profiles-file",
            str(profiles_file),
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["merged_source"] == "UNKNOWN_002"
    assert data["profile"]["id"] == "john"
    assert data["profile"]["name"] == "John"
    assert data["profile"]["embedding_count"] == 2


def test_speakers_merge_self_exits_nonzero(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    _write_duplicate_profile_store(profiles_file)

    result = runner.invoke(
        app,
        [
            "speakers",
            "merge",
            "John",
            "john",
            "--speaker-profiles-file",
            str(profiles_file),
        ],
    )

    assert result.exit_code == 1
    assert "itself" in result.stdout


def test_speakers_review_merges_current_speaker_into_existing_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    audio_file = tmp_path / "recording.wav"
    snippet_file = tmp_path / "snippet.wav"
    audio_file.write_bytes(b"audio")
    snippet_file.write_bytes(b"snippet")
    profiles_file.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": DEFAULT_SPEAKER_EMBEDDING_MODEL,
                "next_unknown_id": 1,
                "profiles": [
                    {
                        "id": "john",
                        "name": "John",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 2.0)]

    with (
        patch("agent_cli.agents.speakers.SpeakerDiarizer", return_value=diarizer),
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={"SPEAKER_00": [0.99, 0.01]},
        ),
        patch("agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file),
        patch("agent_cli.agents.speakers._start_audio_playback"),
    ):
        result = runner.invoke(
            app,
            [
                "speakers",
                "review",
                "--from-file",
                str(audio_file),
                "--speaker-profiles-file",
                str(profiles_file),
                "--hf-token",
                "token",
            ],
            input="m\n\n",
        )

    assert result.exit_code == 0
    assert "Merged current speaker SPEAKER_00 into John" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]


def test_speakers_review_creates_new_named_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    audio_file = tmp_path / "recording.wav"
    snippet_file = tmp_path / "snippet.wav"
    audio_file.write_bytes(b"audio")
    snippet_file.write_bytes(b"snippet")
    profiles_file.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": DEFAULT_SPEAKER_EMBEDDING_MODEL,
                "next_unknown_id": 1,
                "profiles": [],
            },
        )
        + "\n",
        encoding="utf-8",
    )
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 2.0)]

    with (
        patch("agent_cli.agents.speakers.SpeakerDiarizer", return_value=diarizer),
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={"SPEAKER_00": [1.0, 0.0]},
        ),
        patch("agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file),
        patch("agent_cli.agents.speakers._start_audio_playback"),
    ):
        result = runner.invoke(
            app,
            [
                "speakers",
                "review",
                "--from-file",
                str(audio_file),
                "--speaker-profiles-file",
                str(profiles_file),
                "--hf-token",
                "token",
            ],
            input="n\nAlice\n",
        )

    assert result.exit_code == 0
    assert "Created speaker profile Alice" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert store["profiles"][0]["name"] == "Alice"
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0]]


def test_speakers_review_saves_changes_before_quitting(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    audio_file = tmp_path / "recording.wav"
    snippet_file = tmp_path / "snippet.wav"
    audio_file.write_bytes(b"audio")
    snippet_file.write_bytes(b"snippet")
    profiles_file.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": DEFAULT_SPEAKER_EMBEDDING_MODEL,
                "next_unknown_id": 1,
                "profiles": [
                    {
                        "id": "john",
                        "name": "John",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [
        DiarizedSegment("SPEAKER_00", 0.0, 2.0),
        DiarizedSegment("SPEAKER_01", 2.0, 4.0),
    ]

    with (
        patch("agent_cli.agents.speakers.SpeakerDiarizer", return_value=diarizer),
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={
                "SPEAKER_00": [0.99, 0.01],
                "SPEAKER_01": [0.0, 1.0],
            },
        ),
        patch("agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file),
        patch("agent_cli.agents.speakers._start_audio_playback"),
    ):
        result = runner.invoke(
            app,
            [
                "speakers",
                "review",
                "--from-file",
                str(audio_file),
                "--speaker-profiles-file",
                str(profiles_file),
                "--hf-token",
                "token",
            ],
            input="m\n\nq\n",
        )

    assert result.exit_code == 0
    assert "Saved speaker profiles" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]


def test_resolve_review_audio_source_rejects_last_recording_zero(tmp_path: Path) -> None:
    with (
        patch("agent_cli.agents.speakers.get_last_recording") as get_last_recording,
        pytest.raises(ValueError, match="--last-recording must be 1 or greater"),
    ):
        speakers_module._resolve_review_audio_source(
            from_file=None,
            last_recording=0,
            last_session=None,
            transcription_log=tmp_path / "transcriptions.jsonl",
            output_dir=tmp_path,
            session_gap=300.0,
        )

    get_last_recording.assert_not_called()


def test_review_speaker_prompts_while_snippet_is_playing(tmp_path: Path) -> None:
    snippet_file = tmp_path / "snippet.wav"
    snippet_file.write_bytes(b"snippet")
    playback_process = MagicMock()
    playback_process.poll.return_value = None
    events: list[str] = []

    def start_playback(*_args: object, **_kwargs: object) -> MagicMock:
        events.append("start")
        return playback_process

    def prompt_choice() -> str:
        events.append("prompt")
        return "s"

    with (
        patch("agent_cli.agents.speakers._start_audio_playback", side_effect=start_playback),
        patch("agent_cli.agents.speakers._review_choice_prompt", side_effect=prompt_choice),
    ):
        changed = speakers_module._review_speaker(
            label="SPEAKER_00",
            snippet_path=snippet_file,
            embedding=[1.0, 0.0],
            match=None,
            store={"profiles": []},
            player=None,
        )

    assert changed is False
    assert events == ["start", "prompt"]
    playback_process.terminate.assert_called_once_with()
    playback_process.wait.assert_called_once_with(timeout=1.0)
