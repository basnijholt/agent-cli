#!/usr/bin/env python3
"""Profile CLI import times to identify slow imports.

Usage:
    python scripts/profile_imports.py              # Basic timing
    python scripts/profile_imports.py -v           # Verbose (show all imports)
    python scripts/profile_imports.py --top 20     # Show top 20 slowest
    python scripts/profile_imports.py --cli-only   # Just measure CLI startup time

    # Raw importtime output (for detailed analysis):
    python -X importtime -c "from agent_cli.cli import app" 2>&1 | sort -t'|' -k2 -n
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def measure_import_time(module: str, runs: int = 3) -> float:
    """Measure average import time for a module."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            check=False,
            capture_output=True,
            cwd=Path(__file__).parent.parent,
        )
        elapsed = time.perf_counter() - start
        if result.returncode != 0:
            print(f"Error importing {module}: {result.stderr.decode()}")
            return -1
        times.append(elapsed)
    return sum(times) / len(times)


def get_import_breakdown(module: str) -> list[tuple[float, str]]:
    """Get detailed import times using -X importtime."""
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", f"import {module}"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    imports = []
    for line in result.stderr.splitlines():
        if "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) >= 2:  # noqa: PLR2004
            try:
                # importtime format: "import time: self [us] | cumulative | name"
                cumulative = int(parts[1].strip())
                name = parts[2].strip() if len(parts) > 2 else "unknown"  # noqa: PLR2004
                imports.append((cumulative / 1_000_000, name))  # Convert to seconds
            except (ValueError, IndexError):
                continue

    return sorted(imports, reverse=True)


def main() -> None:
    """Run import profiling and display results."""
    parser = argparse.ArgumentParser(description="Profile CLI import times")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all imports")
    parser.add_argument("--top", type=int, default=15, help="Show top N slowest imports")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs for averaging")
    parser.add_argument("--cli-only", action="store_true", help="Only measure CLI import time")
    args = parser.parse_args()

    if args.cli_only:
        avg = measure_import_time("agent_cli.cli", runs=args.runs)
        print(f"CLI import time: {avg:.3f}s (avg of {args.runs} runs)")
        return

    print("=" * 60)
    print("CLI Import Time Profiling")
    print("=" * 60)

    # Measure key entry points
    modules = [
        ("agent_cli", "Base package"),
        ("agent_cli.cli", "CLI app (full)"),
        ("agent_cli.memory", "Memory module (chromadb)"),
        ("agent_cli.rag", "RAG module"),
        ("agent_cli.summarizer", "Summarizer module"),
        ("agent_cli.agents.assistant", "Assistant agent"),
        ("agent_cli.agents.summarize", "Summarize agent"),
        ("pydantic_ai", "pydantic-ai"),
        ("openai", "OpenAI SDK"),
    ]

    print(f"\n{'Module':<30} {'Time (s)':<12} Description")
    print("-" * 60)

    for module, desc in modules:
        avg_time = measure_import_time(module, runs=args.runs)
        if avg_time >= 0:
            bar = "█" * int(avg_time * 20)  # Visual bar (1 block = 50ms)
            print(f"{module:<30} {avg_time:>8.3f}s   {desc} {bar}")

    # Detailed breakdown
    print(f"\n{'=' * 60}")
    print(f"Top {args.top} slowest imports (cumulative time)")
    print("=" * 60)

    imports = get_import_breakdown("agent_cli.cli")

    shown = 0
    for cumtime, name in imports:
        if shown >= args.top and not args.verbose:
            break
        # Skip very fast imports unless verbose
        if cumtime < 0.001 and not args.verbose:  # noqa: PLR2004
            continue
        bar = "█" * int(cumtime * 100)  # 1 block = 10ms
        print(f"{cumtime:>8.3f}s  {name:<40} {bar}")
        shown += 1

    # Summary
    if imports:
        total = imports[0][0] if imports else 0
        print(f"\n{'=' * 60}")
        print(f"Total CLI import time: {total:.3f}s")
        if total > 0.5:  # noqa: PLR2004
            print("⚠️  Import time > 500ms - consider lazy imports")
        elif total > 0.3:  # noqa: PLR2004
            print("⚡ Import time moderate (300-500ms)")
        else:
            print("✅ Import time good (< 300ms)")


if __name__ == "__main__":
    main()
