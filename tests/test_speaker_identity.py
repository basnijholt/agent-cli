"""Tests for persistent speaker identity profiles."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from agent_cli.core.diarization import DiarizedSegment
from agent_cli.core.speaker_identity import (
    SpeakerMatch,
    _normalize_embedding,
    apply_speaker_label_map,
    load_speaker_profile_store,
    match_speaker_profiles,
    parse_speaker_assignments,
    resolve_speaker_identities,
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
