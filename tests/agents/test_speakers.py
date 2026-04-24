"""Tests for speaker profile CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from agent_cli.cli import app
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
