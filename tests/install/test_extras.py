"""Tests for install-extras command."""

from __future__ import annotations

from agent_cli._extras import EXTRAS as EXTRAS_META
from agent_cli.install.extras import EXTRAS, _available_extras


def test_extras_dict_matches_requirements_files() -> None:
    """Ensure extras with requirements files have descriptions.

    Extras defined in _extras.py may or may not have requirements files.
    Those with requirements files (in _requirements/) should have descriptions.
    """
    available = set(_available_extras())
    documented = set(EXTRAS.keys())

    # Only check that extras with requirements files have documentation
    missing_docs = available - documented
    assert not missing_docs, (
        f"Extras missing from EXTRAS dict: {missing_docs}. "
        "Add descriptions for these extras in agent_cli/_extras.py"
    )


def test_extras_metadata_structure() -> None:
    """Ensure EXTRAS metadata in _extras.py has correct structure."""
    assert isinstance(EXTRAS_META, dict)
    for name, value in EXTRAS_META.items():
        assert isinstance(name, str), f"Extra name should be string: {name}"
        assert isinstance(value, tuple), f"Extra {name} value should be tuple"
        assert len(value) == 2, f"Extra {name} should have (desc, packages)"
        desc, packages = value
        assert isinstance(desc, str), f"Extra {name} description should be string"
        assert isinstance(packages, list), f"Extra {name} packages should be list"


def test_install_extras_dict_derives_from_metadata() -> None:
    """Ensure EXTRAS in install/extras.py derives from _extras.py."""
    for name in EXTRAS:
        assert name in EXTRAS_META, f"Extra {name} should be in _extras.py"
        assert EXTRAS[name] == EXTRAS_META[name][0], f"Description mismatch for {name}"
