"""Tests for the release cask updater."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "update_cask.py"
spec = importlib.util.spec_from_file_location("update_cask", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
update_cask = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_cask)
update_cask_text = update_cask.update_cask_text


CASK = """cask "agent-cli" do
  version "0.95.7"
  sha256 "9db4a8d9f44765e1197d687a46e4cde041ada2d5284e6a22324c706d2a40848e"

  url "https://github.com/basnijholt/agent-cli/releases/download/v#{version}/AgentCLI.dmg"
end
"""


def test_update_cask_text_replaces_version_and_sha256() -> None:
    updated = update_cask_text(
        CASK,
        version="v0.95.8",
        sha256="60273504f3c4bea181db64033790e0290bf1b53b86a1386afa3d41216a172029",
    )

    assert '  version "0.95.8"' in updated
    assert '  sha256 "60273504f3c4bea181db64033790e0290bf1b53b86a1386afa3d41216a172029"' in updated
    assert "v#{version}" in updated


def test_update_cask_text_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="sha256"):
        update_cask_text(CASK, version="0.95.8", sha256="bad")


def test_update_cask_text_requires_one_version_stanza() -> None:
    with pytest.raises(ValueError, match="expected exactly one version"):
        update_cask_text(
            CASK.replace('  version "0.95.7"\n', ""),
            version="0.95.8",
            sha256="60273504f3c4bea181db64033790e0290bf1b53b86a1386afa3d41216a172029",
        )
