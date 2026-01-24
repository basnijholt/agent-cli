#!/usr/bin/env python3
"""Check that _extras.py is in sync with pyproject.toml.

This pre-commit hook verifies that:
1. All extras in pyproject.toml (except dev/test) are in _extras.py
2. All extras in _extras.py exist in pyproject.toml

Usage:
    python scripts/check_extras_sync.py
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
EXTRAS_FILE = REPO_ROOT / "agent_cli" / "_extras.py"

# Extras to skip (dev/test dependencies, not runtime installable)
SKIP_EXTRAS = {"dev", "test"}


def get_extras_from_pyproject() -> set[str]:
    """Parse optional-dependencies from pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    all_extras = set(data.get("project", {}).get("optional-dependencies", {}).keys())
    return all_extras - SKIP_EXTRAS


def get_extras_from_source() -> set[str]:
    """Parse extras from agent_cli/_extras.py."""
    if not EXTRAS_FILE.exists():
        return set()

    # Execute the file to get the EXTRAS dict
    namespace: dict = {}
    exec(EXTRAS_FILE.read_text(), namespace)  # noqa: S102
    extras_dict = namespace.get("EXTRAS", {})
    return set(extras_dict.keys())


def main() -> int:
    """Check that extras are in sync."""
    pyproject_extras = get_extras_from_pyproject()
    source_extras = get_extras_from_source()

    errors = []

    # Check for extras in pyproject.toml but not in _extras.py
    missing_in_source = pyproject_extras - source_extras
    if missing_in_source:
        errors.append(
            f"Extras in pyproject.toml but not in _extras.py: {sorted(missing_in_source)}",
        )

    # Check for extras in _extras.py but not in pyproject.toml
    extra_in_source = source_extras - pyproject_extras
    if extra_in_source:
        errors.append(
            f"Extras in _extras.py but not in pyproject.toml: {sorted(extra_in_source)}",
        )

    if errors:
        print("ERROR: _extras.py is out of sync with pyproject.toml")
        for error in errors:
            print(f"  - {error}")
        print("\nRun 'python scripts/sync_extras.py' to regenerate _extras.py")
        return 1

    print("OK: _extras.py is in sync with pyproject.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
