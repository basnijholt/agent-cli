"""Tests for the NeMo Whisper backend helpers."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from agent_cli.server.whisper.backends import nemo as backend


def _install_mock_nemo(
    monkeypatch: pytest.MonkeyPatch,
    calls: dict[str, object],
) -> None:
    """Install a minimal mock of nemo.collections.asr in sys.modules."""

    class _ASRModel:
        @staticmethod
        def from_pretrained(*, model_name: str) -> object:
            calls["model_name"] = model_name
            return object()

    nemo_module: Any = ModuleType("nemo")
    collections_module: Any = ModuleType("nemo.collections")
    asr_module: Any = ModuleType("nemo.collections.asr")
    asr_module.models = SimpleNamespace(ASRModel=_ASRModel)

    nemo_module.collections = collections_module
    collections_module.asr = asr_module

    monkeypatch.setitem(sys.modules, "nemo", nemo_module)
    monkeypatch.setitem(sys.modules, "nemo.collections", collections_module)
    monkeypatch.setitem(sys.modules, "nemo.collections.asr", asr_module)


def test_download_model_resolves_parakeet_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure Parakeet shorthand resolves to the expected NeMo model ID."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("parakeet-tdt-0.6b-v2")
    assert resolved == "nvidia/parakeet-tdt-0.6b-v2"
    assert calls["model_name"] == "nvidia/parakeet-tdt-0.6b-v2"


def test_download_model_preserves_repo_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure explicit model IDs are passed through unchanged."""
    calls: dict[str, object] = {}
    _install_mock_nemo(monkeypatch, calls)

    resolved = backend.download_model("nvidia/parakeet-tdt-0.6b-v2")
    assert resolved == "nvidia/parakeet-tdt-0.6b-v2"
    assert calls["model_name"] == "nvidia/parakeet-tdt-0.6b-v2"
