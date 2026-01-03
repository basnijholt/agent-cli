#!/usr/bin/env python3
"""Update all markdown files that use markdown-code-runner for auto-generation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def find_markdown_files_with_code_blocks(docs_dir: Path) -> list[Path]:
    """Find all markdown files containing CODE:START markers."""
    files_with_code = []
    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text()
        if "<!-- CODE:START -->" in content:
            files_with_code.append(md_file)
    return sorted(files_with_code)


def run_markdown_code_runner(files: list[Path]) -> bool:
    """Run markdown-code-runner on all files. Returns True if all succeeded."""
    if not files:
        print("No files with CODE:START markers found.")
        return True

    print(f"Found {len(files)} file(s) with auto-generated content:")
    for f in files:
        print(f"  - {f}")
    print()

    all_success = True
    for file in files:
        print(f"Updating {file}...", end=" ")
        result = subprocess.run(
            ["markdown-code-runner", str(file)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✓")
        else:
            print("✗")
            print(f"  Error: {result.stderr}")
            all_success = False

    return all_success


def main() -> int:
    """Main entry point."""
    docs_dir = Path(__file__).parent
    if not docs_dir.exists():
        print(f"Error: docs directory not found at {docs_dir}")
        return 1

    files = find_markdown_files_with_code_blocks(docs_dir)
    success = run_markdown_code_runner(files)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
