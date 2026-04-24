"""Persistent speaker identity profiles for diarization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_cli.core.diarization import (
    DiarizedSegment,
    _check_pyannote_installed,
    _get_torch_device,
    _load_audio_for_diarization,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


DEFAULT_SPEAKER_PROFILES_FILE = Path.home() / ".config" / "agent-cli" / "speaker-profiles.json"
DEFAULT_SPEAKER_EMBEDDING_MODEL = "pyannote/wespeaker-voxceleb-resnet34-LM"
DEFAULT_SPEAKER_MATCH_THRESHOLD = 0.72
MAX_PROFILE_EMBEDDINGS = 20
MIN_SPEAKER_EMBEDDING_SECONDS = 1.0
MAX_SPEAKER_EMBEDDING_SECONDS = 120.0
_ASSIGNMENT_SPLIT_RE = re.compile(r"\s*[,;]\s*")
_PROFILE_ID_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SpeakerMatch:
    """A matched persistent speaker profile."""

    profile_id: str
    display_name: str
    similarity: float


def parse_speaker_assignments(value: str | None) -> dict[str, str]:
    """Parse CLI assignments like `SPEAKER_00=Alice,SPEAKER_01=Bob`."""
    if not value:
        return {}

    assignments: dict[str, str] = {}
    for raw_item in _ASSIGNMENT_SPLIT_RE.split(value):
        item = raw_item.strip()
        if not item:
            continue
        if "=" in item:
            source, name = item.split("=", 1)
        elif ":" in item:
            source, name = item.split(":", 1)
        else:
            msg = f"Invalid speaker assignment {item!r}. Use LABEL=Name, e.g. SPEAKER_00=Alice."
            raise ValueError(msg)

        source = source.strip()
        name = name.strip()
        if not source or not name:
            msg = f"Invalid speaker assignment {item!r}. Both label and name are required."
            raise ValueError(msg)
        assignments[source] = name
    return assignments


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_store(embedding_model: str = DEFAULT_SPEAKER_EMBEDDING_MODEL) -> dict[str, Any]:
    return {
        "version": 1,
        "embedding_model": embedding_model,
        "next_unknown_id": 1,
        "profiles": [],
    }


def load_speaker_profile_store(
    path: Path,
    *,
    embedding_model: str = DEFAULT_SPEAKER_EMBEDDING_MODEL,
) -> dict[str, Any]:
    """Load persistent speaker identity profiles."""
    path = path.expanduser()
    if not path.exists():
        return _new_store(embedding_model)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"Invalid speaker profile file {path}: {exc}"
        raise ValueError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Invalid speaker profile file {path}: expected a JSON object."
        raise TypeError(msg)

    stored_model = data.get("embedding_model")
    if stored_model and stored_model != embedding_model:
        msg = (
            f"Speaker profile file {path} uses embedding model {stored_model!r}, "
            f"not {embedding_model!r}."
        )
        raise ValueError(msg)

    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        msg = f"Invalid speaker profile file {path}: profiles must be a list."
        raise TypeError(msg)

    data.setdefault("version", 1)
    data["embedding_model"] = embedding_model
    data.setdefault("next_unknown_id", 1)
    return data


def save_speaker_profile_store(path: Path, store: Mapping[str, Any]) -> None:
    """Persist speaker identity profiles."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _profile_display_name(profile: Mapping[str, Any]) -> str:
    name = profile.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    profile_id = profile.get("id")
    return str(profile_id)


def _profile_matches_identifier(profile: Mapping[str, Any], identifier: str) -> bool:
    identifier_lower = identifier.casefold()
    return any(
        isinstance(value, str) and value.casefold() == identifier_lower
        for value in (profile.get("id"), profile.get("name"))
    )


def _find_profile(store: Mapping[str, Any], identifier: str) -> dict[str, Any] | None:
    profiles = store.get("profiles", [])
    if not isinstance(profiles, list):
        return None
    for profile in profiles:
        if isinstance(profile, dict) and _profile_matches_identifier(profile, identifier):
            return profile
    return None


def _slug_profile_id(name: str) -> str:
    slug = _PROFILE_ID_RE.sub("_", name.casefold()).strip("_")
    return slug or "speaker"


def _unique_profile_id(store: Mapping[str, Any], name: str) -> str:
    base_id = _slug_profile_id(name)
    profile_id = base_id
    index = 2
    while _find_profile(store, profile_id) is not None:
        profile_id = f"{base_id}_{index}"
        index += 1
    return profile_id


def _next_unknown_profile_id(store: dict[str, Any]) -> str:
    index = int(store.get("next_unknown_id", 1))
    while _find_profile(store, f"UNKNOWN_{index:03d}") is not None:
        index += 1
    store["next_unknown_id"] = index + 1
    return f"UNKNOWN_{index:03d}"


def _normalize_embedding(values: Any) -> list[float]:
    import numpy as np  # noqa: PLC0415

    embedding = np.asarray(values, dtype=float)
    if embedding.ndim == 0 or embedding.size == 0:
        msg = "Speaker embedding output is empty or scalar; expected a vector."
        raise RuntimeError(msg)
    if embedding.ndim > 1:
        embedding = embedding.reshape(-1, embedding.shape[-1]).mean(axis=0)
    if not np.all(np.isfinite(embedding)):
        msg = "Speaker embedding output contains non-finite values."
        raise RuntimeError(msg)
    norm = float(np.linalg.norm(embedding))
    if not np.isfinite(norm) or norm <= 0:
        msg = "Speaker embedding output has zero norm."
        raise RuntimeError(msg)
    return (embedding / norm).astype(float).tolist()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _profile_similarity(embedding: list[float], profile: Mapping[str, Any]) -> float:
    stored_embeddings = profile.get("embeddings", [])
    if not isinstance(stored_embeddings, list):
        return -1.0
    similarities = [
        _cosine_similarity(embedding, stored)
        for stored in stored_embeddings
        if isinstance(stored, list)
    ]
    return max(similarities, default=-1.0)


def match_speaker_profiles(
    embeddings: Mapping[str, list[float]],
    store: Mapping[str, Any],
    *,
    threshold: float = DEFAULT_SPEAKER_MATCH_THRESHOLD,
) -> dict[str, SpeakerMatch]:
    """Match current diarization labels to persisted speaker profiles."""
    profiles = [profile for profile in store.get("profiles", []) if isinstance(profile, dict)]
    matches: dict[str, SpeakerMatch] = {}
    for label, embedding in embeddings.items():
        best_profile: dict[str, Any] | None = None
        best_similarity = -1.0
        for profile in profiles:
            similarity = _profile_similarity(embedding, profile)
            if similarity > best_similarity:
                best_similarity = similarity
                best_profile = profile
        if best_profile is None or best_similarity < threshold:
            continue
        matches[label] = SpeakerMatch(
            profile_id=str(best_profile["id"]),
            display_name=_profile_display_name(best_profile),
            similarity=best_similarity,
        )
    return matches


def _append_embedding(profile: dict[str, Any], embedding: list[float]) -> None:
    embeddings = profile.setdefault("embeddings", [])
    if not isinstance(embeddings, list):
        embeddings = []
        profile["embeddings"] = embeddings
    embeddings.append(embedding)
    del embeddings[:-MAX_PROFILE_EMBEDDINGS]
    profile["updated_at"] = _now()


def _add_named_embedding(
    store: dict[str, Any],
    name: str,
    embedding: list[float],
    *,
    source_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = source_profile or _find_profile(store, name)
    if profile is None:
        created_at = _now()
        profile = {
            "id": _unique_profile_id(store, name),
            "name": name,
            "anonymous": False,
            "embeddings": [],
            "created_at": created_at,
            "updated_at": created_at,
        }
        store.setdefault("profiles", []).append(profile)
    else:
        profile["name"] = name
        profile["anonymous"] = False
    _append_embedding(profile, embedding)
    return profile


def _add_unknown_embedding(store: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    created_at = _now()
    profile: dict[str, Any] = {
        "id": _next_unknown_profile_id(store),
        "name": None,
        "anonymous": True,
        "embeddings": [],
        "created_at": created_at,
        "updated_at": created_at,
    }
    store.setdefault("profiles", []).append(profile)
    _append_embedding(profile, embedding)
    return profile


def _speaker_waveforms(
    audio_path: Path,
    segments: list[DiarizedSegment],
) -> tuple[dict[str, Any], int]:
    import torch  # noqa: PLC0415

    waveform, sample_rate = _load_audio_for_diarization(audio_path)
    max_samples = int(MAX_SPEAKER_EMBEDDING_SECONDS * sample_rate)
    min_samples = int(MIN_SPEAKER_EMBEDDING_SECONDS * sample_rate)
    by_speaker: dict[str, list[Any]] = {}
    sample_totals: dict[str, int] = {}
    total_samples = waveform.shape[-1]

    for segment in sorted(segments, key=lambda item: (item.speaker, item.start, item.end)):
        if segment.end <= segment.start:
            continue
        current_total = sample_totals.get(segment.speaker, 0)
        if current_total >= max_samples:
            continue
        start = max(0, int(segment.start * sample_rate))
        end = min(total_samples, int(segment.end * sample_rate))
        if end <= start:
            continue
        chunk = waveform[:, start:end]
        remaining = max_samples - current_total
        if chunk.shape[-1] > remaining:
            chunk = chunk[:, :remaining]
        by_speaker.setdefault(segment.speaker, []).append(chunk)
        sample_totals[segment.speaker] = current_total + chunk.shape[-1]

    return {
        speaker: torch.cat(chunks, dim=1)
        for speaker, chunks in by_speaker.items()
        if sample_totals.get(speaker, 0) >= min_samples
    }, sample_rate


def _load_embedding_inference(
    *,
    hf_token: str,
    device: str | None,
    embedding_model: str,
) -> Any:
    _check_pyannote_installed()
    import torch  # noqa: PLC0415
    from pyannote.audio import Inference, Model  # noqa: PLC0415

    model = Model.from_pretrained(embedding_model, token=hf_token)
    if model is None:
        msg = (
            f"Could not load speaker embedding model {embedding_model!r}. "
            "Make sure the HuggingFace token has access to the model."
        )
        raise RuntimeError(msg)
    torch_device = torch.device(device or _get_torch_device())
    return Inference(model, window="whole", device=torch_device)


def extract_speaker_embeddings(
    *,
    audio_path: Path,
    segments: list[DiarizedSegment],
    hf_token: str,
    device: str | None = None,
    embedding_model: str = DEFAULT_SPEAKER_EMBEDDING_MODEL,
) -> dict[str, list[float]]:
    """Extract one normalized embedding for each diarized speaker label."""
    speaker_waveforms, sample_rate = _speaker_waveforms(audio_path, segments)
    if not speaker_waveforms:
        return {}

    inference = _load_embedding_inference(
        hf_token=hf_token,
        device=device,
        embedding_model=embedding_model,
    )
    embeddings: dict[str, list[float]] = {}
    for speaker, waveform in speaker_waveforms.items():
        output = inference({"waveform": waveform, "sample_rate": sample_rate})
        if isinstance(output, tuple):
            output = output[0]
        if hasattr(output, "data"):
            output = output.data
        embeddings[speaker] = _normalize_embedding(output)
    return embeddings


def _speaker_identities_need_embeddings(
    assignments: Mapping[str, str],
    *,
    identify_speakers: bool,
    remember_unknown_speakers: bool,
    store: Mapping[str, Any],
) -> bool:
    """Check whether the current request needs speaker embeddings."""
    return (
        bool(assignments)
        or remember_unknown_speakers
        or (identify_speakers and bool(store.get("profiles")))
    )


def _remember_unknown_profiles(
    store: dict[str, Any],
    embeddings: Mapping[str, list[float]],
    label_map: dict[str, str],
) -> bool:
    """Create anonymous profiles for labels that have not matched yet."""
    changed = False
    for label, embedding in embeddings.items():
        if label in label_map:
            continue
        profile = _add_unknown_embedding(store, embedding)
        label_map[label] = str(profile["id"])
        changed = True
    return changed


def _matches_assignment(
    *,
    label: str,
    mapped_name: str,
    source_label: str,
    matches: Mapping[str, SpeakerMatch],
) -> bool:
    match = matches.get(label)
    return mapped_name == source_label or (match is not None and match.profile_id == source_label)


def _labels_for_assignment(
    source_label: str,
    embeddings: Mapping[str, list[float]],
    label_map: Mapping[str, str],
    matches: Mapping[str, SpeakerMatch],
) -> list[str]:
    """Find current diarized labels referred to by an enrollment assignment."""
    if source_label in embeddings:
        return [source_label]
    return [
        label
        for label, mapped_name in label_map.items()
        if _matches_assignment(
            label=label,
            mapped_name=mapped_name,
            source_label=source_label,
            matches=matches,
        )
    ]


def _enroll_assignment(
    *,
    store: dict[str, Any],
    embeddings: Mapping[str, list[float]],
    label_map: dict[str, str],
    matches: Mapping[str, SpeakerMatch],
    source_label: str,
    name: str,
) -> None:
    """Enroll one current or persisted speaker label into a named profile."""
    labels = _labels_for_assignment(source_label, embeddings, label_map, matches)
    if not labels:
        msg = (
            f"Cannot enroll {source_label!r}: no diarized speaker with that label "
            "was found in this recording."
        )
        raise ValueError(msg)

    source_profile = _find_profile(store, source_label)
    should_rename_source = source_profile is not None and source_profile.get("anonymous")
    for label in labels:
        if should_rename_source:
            _add_named_embedding(
                store,
                name,
                embeddings[label],
                source_profile=source_profile,
            )
        else:
            _add_named_embedding(store, name, embeddings[label])
        label_map[label] = name


def resolve_speaker_identities(
    *,
    audio_path: Path,
    segments: list[DiarizedSegment],
    hf_token: str,
    profiles_file: Path | None = DEFAULT_SPEAKER_PROFILES_FILE,
    enroll_speakers: str | None = None,
    identify_speakers: bool = True,
    remember_unknown_speakers: bool = False,
    threshold: float = DEFAULT_SPEAKER_MATCH_THRESHOLD,
    device: str | None = None,
    embedding_model: str = DEFAULT_SPEAKER_EMBEDDING_MODEL,
) -> dict[str, str]:
    """Resolve current diarization labels to persistent speaker names."""
    assignments = parse_speaker_assignments(enroll_speakers)
    path = (profiles_file or DEFAULT_SPEAKER_PROFILES_FILE).expanduser()
    store = load_speaker_profile_store(path, embedding_model=embedding_model)
    if not _speaker_identities_need_embeddings(
        assignments,
        identify_speakers=identify_speakers,
        remember_unknown_speakers=remember_unknown_speakers,
        store=store,
    ):
        return {}

    embeddings = extract_speaker_embeddings(
        audio_path=audio_path,
        segments=segments,
        hf_token=hf_token,
        device=device,
        embedding_model=embedding_model,
    )
    if not embeddings:
        if assignments:
            msg = "Could not extract speaker embeddings for enrollment."
            raise RuntimeError(msg)
        return {}

    changed = False
    label_map: dict[str, str] = {}
    matches: dict[str, SpeakerMatch] = {}
    if identify_speakers:
        matches = match_speaker_profiles(embeddings, store, threshold=threshold)
        label_map.update({label: match.display_name for label, match in matches.items()})

    if remember_unknown_speakers:
        changed = _remember_unknown_profiles(store, embeddings, label_map)

    for source_label, name in assignments.items():
        _enroll_assignment(
            store=store,
            embeddings=embeddings,
            label_map=label_map,
            matches=matches,
            source_label=source_label,
            name=name,
        )
        changed = True

    if changed:
        save_speaker_profile_store(path, store)

    return label_map


def apply_speaker_label_map(
    segments: list[DiarizedSegment],
    label_map: Mapping[str, str],
) -> list[DiarizedSegment]:
    """Replace diarization labels, merging adjacent identical resolved speakers."""
    if not label_map:
        return segments

    renamed: list[DiarizedSegment] = []
    for segment in segments:
        speaker = label_map.get(segment.speaker, segment.speaker)
        if renamed and renamed[-1].speaker == speaker:
            previous = renamed[-1]
            text = " ".join(part for part in (previous.text, segment.text) if part)
            renamed[-1] = DiarizedSegment(
                speaker=speaker,
                start=previous.start,
                end=segment.end,
                text=text,
            )
            continue
        renamed.append(
            DiarizedSegment(
                speaker=speaker,
                start=segment.start,
                end=segment.end,
                text=segment.text,
            ),
        )
    return renamed
