"""Tests for install-extras command."""

from __future__ import annotations

from agent_cli.install.extras import EXTRAS, _available_extras


def test_extras_dict_matches_requirements_files() -> None:
    """Ensure EXTRAS dict has descriptions for all available extras.

    If this test fails, add the missing extra to EXTRAS in extras.py.
    """
    available = set(_available_extras())
    documented = set(EXTRAS.keys())

    missing_docs = available - documented
    extra_docs = documented - available

    assert not missing_docs, (
        f"Extras missing from EXTRAS dict: {missing_docs}. "
        "Add descriptions for these extras in agent_cli/install/extras.py"
    )
    assert not extra_docs, (
        f"Extras in EXTRAS dict but no requirements file: {extra_docs}. "
        "Remove these from EXTRAS or generate the requirements file."
    )
