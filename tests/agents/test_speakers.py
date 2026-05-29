"""Tests for speaker profile CLI commands."""

from __future__ import annotations

import json
import tomllib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import agent_cli.config as config_module
from agent_cli.agents import speakers as speakers_module
from agent_cli.cli import app
from agent_cli.core.diarization import DiarizedSegment, best_clean_speaker_segment
from agent_cli.core.speaker_identity import DEFAULT_SPEAKER_EMBEDDING_MODEL

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def _toml_path(path: str | Path) -> str:
    return json.dumps(str(path))


def test_toml_path_escapes_windows_backslashes() -> None:
    windows_path = r"C:\Users\Bas\AppData\Local\agent-cli\speaker-profiles.json"

    data = tomllib.loads(f"speaker-profiles-file = {_toml_path(windows_path)}")

    assert data["speaker-profiles-file"] == windows_path


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
speaker-profiles-file = {_toml_path(default_profiles_file)}

[speakers]
speaker-profiles-file = {_toml_path(profiles_file)}
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
speaker-profiles-file = {_toml_path(profiles_file)}
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
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0]]


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
    assert data["profile"]["embedding_count"] == 1


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


def test_best_review_segment_prefers_isolated_turn() -> None:
    overlapping_long = DiarizedSegment("SPEAKER_00", 0.0, 5.0)
    other_speaker = DiarizedSegment("SPEAKER_01", 2.0, 3.0)
    isolated_short = DiarizedSegment("SPEAKER_00", 8.0, 10.0)

    segment = best_clean_speaker_segment(
        [overlapping_long, other_speaker, isolated_short],
        "SPEAKER_00",
    )

    assert segment == isolated_short


def test_speakers_review_creates_profile_for_unmatched_speaker_labels(tmp_path: Path) -> None:
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
            return_value={"SPEAKER_00": [0.0, 1.0]},
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
    assert "Speaker: SPEAKER_00" in result.stdout
    assert "Closest profile: none" in result.stdout
    assert "Created speaker profile Alice" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert [profile["name"] for profile in store["profiles"]] == ["John", "Alice"]
    assert store["profiles"][1]["embeddings"] == [[0.0, 1.0]]


def test_speakers_review_creates_profile_when_no_profiles_exist(tmp_path: Path) -> None:
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
    assert "Speaker: SPEAKER_00" in result.stdout
    assert "Closest profile: none" in result.stdout
    assert "Created speaker profile Alice" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert store["profiles"][0]["name"] == "Alice"
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0]]


def test_speakers_review_prints_skipped_named_speaker_matches(tmp_path: Path) -> None:
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
            return_value={"SPEAKER_00": [1.0, 0.0]},
        ),
        patch(
            "agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file
        ) as write_snippet,
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
                "--review-state-file",
                str(tmp_path / "speaker-review-state.json"),
                "--hf-token",
                "token",
            ],
        )

    assert result.exit_code == 0
    assert "Skipped named speaker matches:" in result.stdout
    assert "SPEAKER_00 -> John (john, 1.00)" in result.stdout
    write_snippet.assert_not_called()


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
                    {
                        "id": "UNKNOWN_001",
                        "name": None,
                        "anonymous": True,
                        "embeddings": [[0.0, 1.0]],
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
                "SPEAKER_00": [0.0, 1.0],
                "SPEAKER_01": [0.5, 0.5],
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
    assert [profile["id"] for profile in store["profiles"]] == ["john"]
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.0, 1.0]]


def test_speakers_review_skips_named_profile_matches(tmp_path: Path) -> None:
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
                "next_unknown_id": 2,
                "profiles": [
                    {
                        "id": "john",
                        "name": "John",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                    {
                        "id": "UNKNOWN_001",
                        "name": None,
                        "anonymous": True,
                        "embeddings": [[0.0, 1.0]],
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
                "SPEAKER_00": [1.0, 0.0],
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
            input="n\nAlice\n",
        )

    assert result.exit_code == 0
    assert "Speaker: UNKNOWN_001" in result.stdout
    assert "Speaker: SPEAKER_00" not in result.stdout
    assert "Named speaker UNKNOWN_001 as Alice" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert len(store["profiles"]) == 2
    assert store["profiles"][1]["id"] == "UNKNOWN_001"
    assert store["profiles"][1]["name"] == "Alice"
    assert store["profiles"][1]["anonymous"] is False
    assert store["profiles"][1]["embeddings"] == [[0.0, 1.0]]


def test_speakers_review_merges_anonymous_profile_into_named_profile(tmp_path: Path) -> None:
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
                "next_unknown_id": 2,
                "profiles": [
                    {
                        "id": "john",
                        "name": "John",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                    {
                        "id": "UNKNOWN_001",
                        "name": None,
                        "anonymous": True,
                        "embeddings": [[0.0, 1.0]],
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
            return_value={"SPEAKER_00": [0.0, 1.0]},
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
    assert "Actions:" in result.stdout
    assert "Merge targets:" in result.stdout
    assert "1. John (john)" in result.stdout
    assert "Merge into profile number [1]" in result.stdout
    assert "Merged current speaker UNKNOWN_001 into John" in result.stdout
    store = json.loads(profiles_file.read_text(encoding="utf-8"))
    assert [profile["id"] for profile in store["profiles"]] == ["john"]
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.0, 1.0]]


def test_resolve_review_audio_targets_rejects_last_recording_zero(tmp_path: Path) -> None:
    with (
        patch("agent_cli.agents.speakers.get_last_recording") as get_last_recording,
        pytest.raises(ValueError, match="--last-recording must be 1 or greater"),
    ):
        speakers_module._resolve_review_audio_targets(
            from_file=None,
            last_recording=0,
            last_session=None,
            transcription_log=tmp_path / "transcriptions.jsonl",
            session_gap=300.0,
        )

    get_last_recording.assert_not_called()


def test_resolve_review_audio_targets_defaults_to_last_live_session(tmp_path: Path) -> None:
    transcription_log = tmp_path / "transcriptions.jsonl"
    audio_file = tmp_path / "live.wav"
    audio_file.write_bytes(b"audio")
    transcription_log.write_text(
        json.dumps(
            {
                "timestamp": "2026-04-30T12:00:00+00:00",
                "audio_file": str(audio_file),
                "duration_seconds": 1.0,
            },
        )
        + "\n",
        encoding="utf-8",
    )

    with patch("agent_cli.agents.speakers.get_last_recording") as get_last_recording:
        targets = speakers_module._resolve_review_audio_targets(
            from_file=None,
            last_recording=None,
            last_session=None,
            transcription_log=transcription_log,
            session_gap=300.0,
        )

    assert targets == [audio_file]
    get_last_recording.assert_not_called()


def test_resolve_review_audio_targets_walks_live_files_newest_first(tmp_path: Path) -> None:
    transcription_log = tmp_path / "transcriptions.jsonl"
    older_audio = tmp_path / "older.wav"
    newer_audio = tmp_path / "newer.wav"
    older_audio.write_bytes(b"older")
    newer_audio.write_bytes(b"newer")
    entries = [
        {
            "timestamp": "2026-04-30T12:00:00+00:00",
            "audio_file": str(older_audio),
            "duration_seconds": 1.0,
        },
        {
            "timestamp": "2026-04-30T12:01:00+00:00",
            "audio_file": str(newer_audio),
            "duration_seconds": 1.0,
        },
    ]
    transcription_log.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )

    targets = speakers_module._resolve_review_audio_targets(
        from_file=None,
        last_recording=None,
        last_session=None,
        transcription_log=transcription_log,
        session_gap=300.0,
    )

    assert targets == [newer_audio, older_audio]


def test_review_audio_targets_skips_cached_audio(tmp_path: Path) -> None:
    audio_file = tmp_path / "reviewed.wav"
    audio_file.write_bytes(b"audio")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}}
    speakers_module._record_audio_review(review_state, audio_file, [])
    diarizer = MagicMock()
    store: dict[str, object] = {"profiles": []}

    changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
        audio_targets=[audio_file],
        review_state=review_state,
        store=store,
        diarizer=diarizer,
        hf_token="token",  # noqa: S106
        speaker_match_threshold=0.7,
        snippet_seconds=6.0,
        player=None,
        force_review=False,
        review_state_path=tmp_path / "speaker-review-state.json",
    )

    assert changed is False
    assert reviewed_count == 0
    assert skipped_count == 1
    assert interrupted is False
    diarizer.diarize.assert_not_called()


def test_review_audio_targets_saves_state_after_each_reviewed_audio(tmp_path: Path) -> None:
    audio_file = tmp_path / "reviewed.wav"
    state_file = tmp_path / "speaker-review-state.json"
    audio_file.write_bytes(b"audio")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = []

    changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
        audio_targets=[audio_file],
        review_state=review_state,
        store={"profiles": []},
        diarizer=diarizer,
        hf_token="token",  # noqa: S106
        speaker_match_threshold=0.7,
        snippet_seconds=6.0,
        player=None,
        force_review=False,
        review_state_path=state_file,
    )

    assert changed is False
    assert reviewed_count == 1
    assert skipped_count == 0
    assert interrupted is False
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert speakers_module._audio_review_key(audio_file) in saved_state["audio_files"]


def test_review_audio_targets_remembers_skipped_speaker_across_audio(
    tmp_path: Path,
) -> None:
    first_audio = tmp_path / "first.wav"
    second_audio = tmp_path / "second.wav"
    state_file = tmp_path / "speaker-review-state.json"
    snippet_file = tmp_path / "snippet.wav"
    first_audio.write_bytes(b"first")
    second_audio.write_bytes(b"second")
    snippet_file.write_bytes(b"snippet")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 3.0)]

    with (
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={"SPEAKER_00": [1.0, 0.0]},
        ),
        patch(
            "agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file
        ) as write_snippet,
        patch("agent_cli.agents.speakers._start_audio_playback"),
        patch("agent_cli.agents.speakers._review_choice_prompt", return_value="s") as prompt,
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[first_audio, second_audio],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 2
    assert skipped_count == 0
    assert interrupted is False
    write_snippet.assert_called_once()
    prompt.assert_called_once()
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["skipped_speakers"][0]["embeddings"] == [[1.0, 0.0]]
    second_key = speakers_module._audio_review_key(second_audio)
    assert saved_state["audio_files"][second_key]["speakers"][0]["action"] == "skipped_cached"


def test_review_audio_targets_does_not_auto_skip_loose_skipped_speaker_match(
    tmp_path: Path,
) -> None:
    first_audio = tmp_path / "first.wav"
    second_audio = tmp_path / "second.wav"
    state_file = tmp_path / "speaker-review-state.json"
    snippet_file = tmp_path / "snippet.wav"
    first_audio.write_bytes(b"first")
    second_audio.write_bytes(b"second")
    snippet_file.write_bytes(b"snippet")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 3.0)]

    with (
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            side_effect=[
                {"SPEAKER_00": [1.0, 0.0]},
                {"SPEAKER_00": [0.8, 0.6]},
            ],
        ),
        patch(
            "agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file
        ) as write_snippet,
        patch("agent_cli.agents.speakers._start_audio_playback"),
        patch("agent_cli.agents.speakers._review_choice_prompt", return_value="s") as prompt,
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[first_audio, second_audio],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 2
    assert skipped_count == 0
    assert interrupted is False
    assert write_snippet.call_count == 2
    assert prompt.call_count == 2
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    second_key = speakers_module._audio_review_key(second_audio)
    assert saved_state["audio_files"][second_key]["speakers"][0]["action"] == "skipped"


def test_review_audio_targets_does_not_cache_interrupted_audio(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "recording.wav"
    state_file = tmp_path / "speaker-review-state.json"
    snippet_file = tmp_path / "snippet.wav"
    audio_file.write_bytes(b"audio")
    snippet_file.write_bytes(b"snippet")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [
        DiarizedSegment("SPEAKER_00", 0.0, 3.0),
        DiarizedSegment("SPEAKER_01", 4.0, 7.0),
    ]

    with (
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={
                "SPEAKER_00": [1.0, 0.0],
                "SPEAKER_01": [0.0, 1.0],
            },
        ),
        patch("agent_cli.agents.speakers._write_speaker_snippet", return_value=snippet_file),
        patch("agent_cli.agents.speakers._start_audio_playback"),
        patch("agent_cli.agents.speakers._review_choice_prompt", side_effect=["s", "q"]),
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[audio_file],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 0
    assert skipped_count == 0
    assert interrupted is True
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["audio_files"] == {}
    assert saved_state["skipped_speakers"][0]["embeddings"] == [[1.0, 0.0]]


def test_review_audio_targets_does_not_cache_audio_when_snippet_fails(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "recording.wav"
    state_file = tmp_path / "speaker-review-state.json"
    audio_file.write_bytes(b"audio")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 3.0)]

    with (
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={"SPEAKER_00": [1.0, 0.0]},
        ),
        patch(
            "agent_cli.agents.speakers._write_speaker_snippet",
            side_effect=RuntimeError("ffmpeg is required"),
        ),
        patch("agent_cli.agents.speakers._review_choice_prompt") as prompt,
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[audio_file],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 0
    assert skipped_count == 0
    assert interrupted is False
    prompt.assert_not_called()
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["audio_files"] == {}


def test_review_audio_targets_auto_skips_short_fragments(tmp_path: Path) -> None:
    audio_file = tmp_path / "short.wav"
    state_file = tmp_path / "speaker-review-state.json"
    audio_file.write_bytes(b"audio")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 1.5)]

    with (
        patch(
            "agent_cli.agents.speakers.extract_speaker_embeddings",
            return_value={"SPEAKER_00": [1.0, 0.0]},
        ),
        patch("agent_cli.agents.speakers._write_speaker_snippet") as write_snippet,
        patch("agent_cli.agents.speakers._review_choice_prompt") as prompt,
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[audio_file],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 1
    assert skipped_count == 0
    assert interrupted is False
    write_snippet.assert_not_called()
    prompt.assert_not_called()
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    audio_key = speakers_module._audio_review_key(audio_file)
    assert saved_state["audio_files"][audio_key]["speakers"][0]["action"] == "skipped_short"


def test_review_audio_targets_auto_skips_speakers_without_embeddings(
    tmp_path: Path,
) -> None:
    audio_file = tmp_path / "recording.wav"
    state_file = tmp_path / "speaker-review-state.json"
    audio_file.write_bytes(b"audio")
    review_state: dict[str, object] = {"version": 1, "audio_files": {}, "skipped_speakers": []}
    diarizer = MagicMock()
    diarizer.device = "cpu"
    diarizer.diarize.return_value = [DiarizedSegment("SPEAKER_00", 0.0, 3.0)]

    with (
        patch("agent_cli.agents.speakers.extract_speaker_embeddings", return_value={}),
        patch("agent_cli.agents.speakers._write_speaker_snippet") as write_snippet,
        patch("agent_cli.agents.speakers._review_choice_prompt") as prompt,
    ):
        changed, reviewed_count, skipped_count, interrupted = speakers_module._review_audio_targets(
            audio_targets=[audio_file],
            review_state=review_state,
            store={"profiles": []},
            diarizer=diarizer,
            hf_token="token",  # noqa: S106
            speaker_match_threshold=0.7,
            snippet_seconds=6.0,
            player=None,
            force_review=False,
            review_state_path=state_file,
        )

    assert changed is False
    assert reviewed_count == 1
    assert skipped_count == 0
    assert interrupted is False
    write_snippet.assert_not_called()
    prompt.assert_not_called()
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    audio_key = speakers_module._audio_review_key(audio_file)
    assert saved_state["audio_files"][audio_key]["speakers"][0]["action"] == (
        "skipped_no_embedding"
    )


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
        result = speakers_module._review_speaker(
            label="SPEAKER_00",
            snippet_path=snippet_file,
            embedding=[1.0, 0.0],
            match=None,
            store={"profiles": []},
            player=None,
        )

    assert result.changed is False
    assert result.action == "skipped"
    assert events == ["start", "prompt"]
    playback_process.terminate.assert_called_once_with()
    playback_process.wait.assert_called_once_with(timeout=1.0)


def test_review_speaker_without_embedding_does_not_replay_after_invalid_choice(
    tmp_path: Path,
) -> None:
    snippet_file = tmp_path / "snippet.wav"
    snippet_file.write_bytes(b"snippet")
    playback_process = MagicMock()

    with (
        patch(
            "agent_cli.agents.speakers._start_audio_playback", return_value=playback_process
        ) as start,
        patch("agent_cli.agents.speakers._review_choice_prompt", side_effect=["m", "s"]),
    ):
        result = speakers_module._review_speaker(
            label="SPEAKER_00",
            snippet_path=snippet_file,
            embedding=None,
            match=None,
            store={"profiles": []},
            player=None,
        )

    assert result.changed is False
    assert result.action == "skipped"
    start.assert_called_once_with(snippet_file, player=None)
