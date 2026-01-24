#!/usr/bin/env python3
"""Generate requirements files for optional extras from uv.lock.

Usage:
    python .github/scripts/sync_requirements.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
REQ_DIR = REPO_ROOT / "agent_cli" / "_requirements"

EXTRAS = ["rag", "memory", "vad", "whisper", "whisper-mlx", "tts", "tts-kokoro", "server"]


def main() -> None:
    """Generate requirements files from uv.lock."""
    REQ_DIR.mkdir(parents=True, exist_ok=True)

    for extra in EXTRAS:
        print(f"Generating: {extra}")
        output_file = REQ_DIR / f"{extra}.txt"
        cmd = [
            "uv",
            "export",
            "--extra",
            extra,
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "-o",
            str(output_file),
        ]
        result = subprocess.run(cmd, check=False, capture_output=True)
        if result.returncode != 0:
            print(f"Failed to generate {extra}: {result.stderr.decode()}", file=sys.stderr)
            sys.exit(1)

    print(f"Generated {len(EXTRAS)} requirements files")


if __name__ == "__main__":
    main()
