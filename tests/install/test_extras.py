"""Tests for install-extras command."""

from __future__ import annotations

import typing

from agent_cli.core.deps import EXTRAS as EXTRAS_META
from agent_cli.install.extras import EXTRAS, _available_extras, install_extras


def test_extras_dict_matches_requirements_files() -> None:
    """Ensure extras with requirements files have descriptions.

    Extras defined in _extras.json may or may not have requirements files.
    Those with requirements files (in _requirements/) should have descriptions.
    """
    available = set(_available_extras())
    documented = set(EXTRAS.keys())

    # Only check that extras with requirements files have documentation
    missing_docs = available - documented
    assert not missing_docs, (
        f"Extras missing from EXTRAS dict: {missing_docs}. "
        "Add descriptions for these extras in agent_cli/_extras.json"
    )


def test_extras_metadata_structure() -> None:
    """Ensure EXTRAS metadata in _extras.json has correct structure."""
    assert isinstance(EXTRAS_META, dict)
    for name, value in EXTRAS_META.items():
        assert isinstance(name, str), f"Extra name should be string: {name}"
        assert isinstance(value, tuple), f"Extra {name} value should be tuple"
        assert len(value) == 2, f"Extra {name} should have (desc, packages)"
        desc, packages = value
        assert isinstance(desc, str), f"Extra {name} description should be string"
        assert isinstance(packages, list), f"Extra {name} packages should be list"


def test_install_extras_dict_derives_from_metadata() -> None:
    """Ensure EXTRAS in install/extras.py derives from _extras.json."""
    for name in EXTRAS:
        assert name in EXTRAS_META, f"Extra {name} should be in _extras.json"
        assert EXTRAS[name] == EXTRAS_META[name][0], f"Description mismatch for {name}"


def test_install_extras_help_lists_all_extras() -> None:
    """Ensure the install_extras help text mentions all available extras.

    When new extras are added to _extras.json, the docstring and argument help
    in install_extras() must be updated to include them. This test catches
    missing extras in the help text.
    """
    available = set(_available_extras())
    docstring = install_extras.__doc__ or ""

    # Get the argument help text from Annotated metadata
    # The type hint is Annotated[..., typer.Argument(help="...")]
    hints = typing.get_type_hints(install_extras, include_extras=True)
    extras_hint = hints["extras"]
    arg_help = extras_hint.__metadata__[0].help  # typer.models.ArgumentInfo.help

    missing_in_docstring = [e for e in available if f"`{e}`" not in docstring]
    missing_in_arg_help = [e for e in available if f"`{e}`" not in arg_help]

    assert not missing_in_docstring, (
        f"Extras missing from install_extras docstring: {missing_in_docstring}. "
        "Update the docstring in agent_cli/install/extras.py to include these extras."
    )
    assert not missing_in_arg_help, (
        f"Extras missing from install_extras argument help: {missing_in_arg_help}. "
        "Update the 'extras' argument help text in agent_cli/install/extras.py."
    )
