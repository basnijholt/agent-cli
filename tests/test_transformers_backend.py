"""Tests for the transformers Whisper backend helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from agent_cli.server.whisper.backends import transformers as backend


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
