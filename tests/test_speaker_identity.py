"""Tests for persistent speaker identity profiles."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent_cli.core.diarization import DiarizedSegment
from agent_cli.core.speaker_identity import (
    DEFAULT_SPEAKER_MATCH_THRESHOLD,
    SpeakerMatch,
    _normalize_embedding,
    add_speaker_embedding_to_profile,
    apply_speaker_label_map,
    create_speaker_profile_from_embedding,
    load_speaker_profile_store,
    match_speaker_profiles,
    merge_speaker_profiles,
    parse_speaker_assignments,
    rename_speaker_profile,
    resolve_speaker_identities,
    summarize_speaker_profiles,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_speaker_assignments_accepts_commas_and_semicolons() -> None:
    assert parse_speaker_assignments("SPEAKER_00=Alice, SPEAKER_01:Bob;SPEAKER_02=Carol") == {
        "SPEAKER_00": "Alice",
        "SPEAKER_01": "Bob",
        "SPEAKER_02": "Carol",
    }


def test_match_speaker_profiles_uses_similarity_threshold() -> None:
    store = {
        "profiles": [
            {
                "id": "alice",
                "name": "Alice",
                "embeddings": [[1.0, 0.0]],
            },
            {
                "id": "bob",
                "name": "Bob",
                "embeddings": [[0.0, 1.0]],
            },
        ],
    }

    matches = match_speaker_profiles(
        {
            "SPEAKER_00": [0.99, 0.01],
            "SPEAKER_01": [0.4, 0.6],
        },
        store,
        threshold=0.9,
    )

    assert matches == {
        "SPEAKER_00": SpeakerMatch(
            profile_id="alice",
            display_name="Alice",
            similarity=0.99,
        ),
    }


def test_match_speaker_profiles_uses_profile_centroid() -> None:
    store = {
        "profiles": [
            {
                "id": "alice",
                "name": "Alice",
                "embeddings": [[1.0, 0.0], [0.0, 1.0]],
            },
        ],
    }

    matches = match_speaker_profiles(
        {"SPEAKER_00": [0.70710678, 0.70710678]},
        store,
        threshold=0.9,
    )

    assert matches == {
        "SPEAKER_00": SpeakerMatch(
            profile_id="alice",
            display_name="Alice",
            similarity=pytest.approx(1.0),
        ),
    }


def test_default_speaker_match_threshold_allows_repeat_recording_variance() -> None:
    assert DEFAULT_SPEAKER_MATCH_THRESHOLD <= 0.7


def test_normalize_embedding_rejects_non_finite_values() -> None:
    with pytest.raises(RuntimeError, match="non-finite"):
        _normalize_embedding([float("nan"), 1.0])


def test_resolve_speaker_identities_enrolls_named_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]

    with patch(
        "agent_cli.core.speaker_identity.extract_speaker_embeddings",
        return_value={"SPEAKER_00": [1.0, 0.0]},
    ):
        label_map = resolve_speaker_identities(
            audio_path=tmp_path / "audio.wav",
            segments=segments,
            hf_token="token",  # noqa: S106
            profiles_file=profiles_file,
            enroll_speakers="SPEAKER_00=Alice",
        )

    assert label_map == {"SPEAKER_00": "Alice"}
    store = load_speaker_profile_store(profiles_file)
    assert store["profiles"][0]["name"] == "Alice"
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0]]


def test_resolve_speaker_identities_enrolls_before_remembering_unknowns(
    tmp_path: Path,
) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]

    with patch(
        "agent_cli.core.speaker_identity.extract_speaker_embeddings",
        return_value={"SPEAKER_00": [1.0, 0.0]},
    ):
        label_map = resolve_speaker_identities(
            audio_path=tmp_path / "audio.wav",
            segments=segments,
            hf_token="token",  # noqa: S106
            profiles_file=profiles_file,
            enroll_speakers="SPEAKER_00=Alice",
            remember_unknown_speakers=True,
        )

    assert label_map == {"SPEAKER_00": "Alice"}
    store = load_speaker_profile_store(profiles_file)
    assert len(store["profiles"]) == 1
    assert store["profiles"][0]["name"] == "Alice"
    assert store["profiles"][0]["anonymous"] is False


def test_resolve_speaker_identities_matches_existing_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    profiles_file.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": "pyannote/wespeaker-voxceleb-resnet34-LM",
                "next_unknown_id": 1,
                "profiles": [
                    {
                        "id": "alice",
                        "name": "Alice",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )
    segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]

    with patch(
        "agent_cli.core.speaker_identity.extract_speaker_embeddings",
        return_value={"SPEAKER_00": [0.99, 0.01]},
    ):
        label_map = resolve_speaker_identities(
            audio_path=tmp_path / "audio.wav",
            segments=segments,
            hf_token="token",  # noqa: S106
            profiles_file=profiles_file,
            threshold=0.9,
        )

    assert label_map == {"SPEAKER_00": "Alice"}


def test_resolve_speaker_identities_refreshes_matched_profile_when_remembering(
    tmp_path: Path,
) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    profiles_file.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": "pyannote/wespeaker-voxceleb-resnet34-LM",
                "next_unknown_id": 1,
                "profiles": [
                    {
                        "id": "alice",
                        "name": "Alice",
                        "anonymous": False,
                        "embeddings": [[1.0, 0.0]],
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )
    segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]

    with patch(
        "agent_cli.core.speaker_identity.extract_speaker_embeddings",
        return_value={"SPEAKER_00": [0.99, 0.01]},
    ):
        label_map = resolve_speaker_identities(
            audio_path=tmp_path / "audio.wav",
            segments=segments,
            hf_token="token",  # noqa: S106
            profiles_file=profiles_file,
            remember_unknown_speakers=True,
            threshold=0.9,
        )

    assert label_map == {"SPEAKER_00": "Alice"}
    store = load_speaker_profile_store(profiles_file)
    assert len(store["profiles"]) == 1
    assert store["profiles"][0]["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]


def test_resolve_speaker_identities_remembers_unknown_profile(tmp_path: Path) -> None:
    profiles_file = tmp_path / "speaker-profiles.json"
    segments = [DiarizedSegment(speaker="SPEAKER_00", start=0.0, end=2.0)]

    with patch(
        "agent_cli.core.speaker_identity.extract_speaker_embeddings",
        return_value={"SPEAKER_00": [0.0, 1.0]},
    ):
        label_map = resolve_speaker_identities(
            audio_path=tmp_path / "audio.wav",
            segments=segments,
            hf_token="token",  # noqa: S106
            profiles_file=profiles_file,
            remember_unknown_speakers=True,
        )

    assert label_map == {"SPEAKER_00": "UNKNOWN_001"}
    store = load_speaker_profile_store(profiles_file)
    assert store["profiles"][0]["id"] == "UNKNOWN_001"
    assert store["profiles"][0]["anonymous"] is True


def test_rename_speaker_profile_preserves_unknown_profile_id() -> None:
    store = {
        "profiles": [
            {
                "id": "UNKNOWN_001",
                "name": None,
                "anonymous": True,
                "embeddings": [[0.0, 1.0]],
            },
        ],
    }

    profile = rename_speaker_profile(store, "UNKNOWN_001", "John")

    assert profile["id"] == "UNKNOWN_001"
    assert profile["name"] == "John"
    assert profile["anonymous"] is False
    assert profile["embeddings"] == [[0.0, 1.0]]


def test_rename_speaker_profile_rejects_duplicate_names() -> None:
    store = {
        "profiles": [
            {"id": "UNKNOWN_001", "name": None, "embeddings": [[1.0, 0.0]]},
            {"id": "john", "name": "John", "embeddings": [[0.0, 1.0]]},
        ],
    }

    with pytest.raises(ValueError, match="already uses"):
        rename_speaker_profile(store, "UNKNOWN_001", "John")


def test_merge_speaker_profiles_moves_embeddings_and_removes_source() -> None:
    store: dict[str, Any] = {
        "profiles": [
            {
                "id": "john",
                "name": "John",
                "anonymous": False,
                "embeddings": [[1.0, 0.0]],
            },
            {
                "id": "UNKNOWN_002",
                "name": None,
                "anonymous": True,
                "embeddings": [[0.99, 0.01]],
            },
        ],
    }

    profile = merge_speaker_profiles(store, "UNKNOWN_002", "John")

    assert profile["id"] == "john"
    assert profile["name"] == "John"
    assert profile["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]
    assert [stored_profile["id"] for stored_profile in store["profiles"]] == ["john"]


def test_merge_speaker_profiles_rejects_self_merge() -> None:
    store = {
        "profiles": [
            {"id": "john", "name": "John", "embeddings": [[1.0, 0.0]]},
        ],
    }

    with pytest.raises(ValueError, match="itself"):
        merge_speaker_profiles(store, "john", "John")


def test_add_speaker_embedding_to_profile_appends_embedding() -> None:
    store = {
        "profiles": [
            {
                "id": "john",
                "name": "John",
                "anonymous": False,
                "embeddings": [[1.0, 0.0]],
            },
        ],
    }

    profile = add_speaker_embedding_to_profile(store, "John", [0.99, 0.01])

    assert profile["id"] == "john"
    assert profile["embeddings"] == [[1.0, 0.0], [0.99, 0.01]]


def test_create_speaker_profile_from_embedding_rejects_duplicate_name() -> None:
    store = {
        "profiles": [
            {
                "id": "john",
                "name": "John",
                "anonymous": False,
                "embeddings": [[1.0, 0.0]],
            },
        ],
    }

    with pytest.raises(ValueError, match="already uses"):
        create_speaker_profile_from_embedding(store, "John", [0.99, 0.01])


def test_summarize_speaker_profiles_hides_embedding_vectors() -> None:
    store = {
        "profiles": [
            {
                "id": "UNKNOWN_001",
                "name": None,
                "anonymous": True,
                "embeddings": [[0.0, 1.0], [0.1, 0.9]],
            },
        ],
    }

    assert summarize_speaker_profiles(store) == [
        {
            "id": "UNKNOWN_001",
            "name": None,
            "display_name": "UNKNOWN_001",
            "anonymous": True,
            "embedding_count": 2,
            "created_at": None,
            "updated_at": None,
        },
    ]


def test_apply_speaker_label_map_merges_adjacent_matching_labels() -> None:
    segments = [
        DiarizedSegment("SPEAKER_00", 0.0, 1.0, "hello"),
        DiarizedSegment("SPEAKER_01", 1.0, 2.0, "there"),
        DiarizedSegment("SPEAKER_02", 2.0, 3.0, "general"),
    ]

    result = apply_speaker_label_map(
        segments,
        {
            "SPEAKER_00": "Alice",
            "SPEAKER_01": "Alice",
        },
    )

    assert result == [
        DiarizedSegment("Alice", 0.0, 2.0, "hello there"),
        DiarizedSegment("SPEAKER_02", 2.0, 3.0, "general"),
    ]
