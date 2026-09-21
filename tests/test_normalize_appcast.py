"""Tests for normalizing generated Sparkle appcast files."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "normalize_appcast.py"
spec = importlib.util.spec_from_file_location("normalize_appcast", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
normalize_appcast = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalize_appcast)
normalize_appcast_file = normalize_appcast.normalize_appcast_file


def test_normalize_appcast_file_uses_lf_and_final_newline(tmp_path: Path) -> None:
    """Generated appcasts should not need pre-commit auto-fixes."""
    appcast = tmp_path / "appcast.xml"
    appcast.write_bytes(
        b"<rss>\n<description><![CDATA[## What's Changed\r\n\r\n* Item\r\n]]></description>\n</rss>"
    )

    normalize_appcast_file(appcast)

    assert appcast.read_bytes() == (
        b"<rss>\n<description><![CDATA[## What's Changed\n\n* Item\n]]></description>\n</rss>\n"
    )
