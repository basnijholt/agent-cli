#!/usr/bin/env python3
"""Check that plugin skill files are in sync with source files."""

import sys
from pathlib import Path

SYNC_PAIRS = [
    # Plugin marketplace distribution
    ("agent_cli/dev/skill/SKILL.md", ".claude-plugin/skills/agent-cli-dev/SKILL.md"),
    ("agent_cli/dev/skill/examples.md", ".claude-plugin/skills/agent-cli-dev/examples.md"),
    # Project-local skill (for Claude Code working on this repo)
    ("agent_cli/dev/skill/SKILL.md", ".claude/skills/agent-cli-dev/SKILL.md"),
    ("agent_cli/dev/skill/examples.md", ".claude/skills/agent-cli-dev/examples.md"),
]


def main() -> int:
    """Check that plugin skill files match source files."""
    root = Path(__file__).parent.parent
    out_of_sync = []

    for source, target in SYNC_PAIRS:
        source_path = root / source
        target_path = root / target

        if not source_path.exists():
            print(f"Source not found: {source}")
            continue

        if not target_path.exists():
            out_of_sync.append((source, target, "target missing"))
            continue

        if source_path.read_text() != target_path.read_text():
            out_of_sync.append((source, target, "content differs"))

    if out_of_sync:
        print("Plugin skill files are out of sync:")
        for source, target, reason in out_of_sync:
            print(f"  {source} -> {target} ({reason})")
        print("\nRun:")
        print("  cp agent_cli/dev/skill/*.md .claude-plugin/skills/agent-cli-dev/")
        print("  cp agent_cli/dev/skill/*.md .claude/skills/agent-cli-dev/")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
