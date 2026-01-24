#!/usr/bin/env python3
"""Generate _extras.json from pyproject.toml.

This script parses the optional-dependencies in pyproject.toml and generates
the agent_cli/_extras.json file with package-to-import mappings.

Usage:
    python scripts/sync_extras.py
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
EXTRAS_FILE = REPO_ROOT / "agent_cli" / "_extras.json"

# Extras to skip (dev/test dependencies, not runtime installable)
SKIP_EXTRAS = {"dev", "test"}

# Manual mapping of extra name -> (description, list of import names)
# Import names should be the Python module name (how you import it)
# Bundle extras (voice, cloud, full) have empty import lists since they just install other extras
EXTRA_METADATA: dict[str, tuple[str, list[str]]] = {
    # Provider extras (base dependencies now optional)
    "audio": ("Audio recording/playback", ["sounddevice"]),
    "wyoming": ("Wyoming protocol support", ["wyoming"]),
    "openai": ("OpenAI API provider", ["openai"]),
    "gemini": ("Google Gemini provider", ["google.genai"]),
    "llm": ("LLM framework (pydantic-ai)", ["pydantic_ai"]),
    # Feature extras
    "rag": ("RAG proxy (ChromaDB, embeddings)", ["chromadb"]),
    "memory": ("Long-term memory proxy", ["chromadb", "yaml"]),
    "vad": ("Voice Activity Detection (silero-vad)", ["silero_vad"]),
    "whisper": ("Local Whisper ASR (faster-whisper)", ["faster_whisper"]),
    "whisper-mlx": ("MLX Whisper for Apple Silicon", ["mlx_whisper"]),
    "tts": ("Local Piper TTS", ["piper"]),
    "tts-kokoro": ("Kokoro neural TTS", ["kokoro"]),
    "server": ("FastAPI server components", ["fastapi"]),
    "speed": ("Audio speed adjustment (audiostretchy)", ["audiostretchy"]),
}


def get_extras_from_pyproject() -> set[str]:
    """Parse optional-dependencies from pyproject.toml."""
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    all_extras = set(data.get("project", {}).get("optional-dependencies", {}).keys())
    return all_extras - SKIP_EXTRAS


def extract_package_name(dep: str) -> str:
    """Extract the package name from a dependency specification.

    Examples:
        "chromadb>=0.4.22" -> "chromadb"
        "pydantic-ai-slim[openai,duckduckgo]" -> "pydantic-ai-slim"
        'mlx-whisper>=0.4.0; sys_platform == "darwin"' -> "mlx-whisper"

    """
    # Remove markers (;...) and extras ([...])
    dep = re.split(r"[;\[]", dep)[0]
    # Remove version specifiers
    dep = re.split(r"[<>=!~]", dep)[0]
    return dep.strip()


def package_to_import_name(package: str) -> str:
    """Convert a package name to its Python import name.

    Examples:
        "google-genai" -> "google.genai"
        "pydantic-ai-slim" -> "pydantic_ai"
        "silero-vad" -> "silero_vad"
        "faster-whisper" -> "faster_whisper"

    """
    # Special cases where the import name differs significantly
    special_cases = {
        "google-genai": "google.genai",
        "pydantic-ai-slim": "pydantic_ai",
        "silero-vad": "silero_vad",
        "faster-whisper": "faster_whisper",
        "mlx-whisper": "mlx_whisper",
        "piper-tts": "piper",
        "huggingface-hub": "huggingface_hub",
        "fastapi": "fastapi",
        "audiostretchy": "audiostretchy",
    }
    if package in special_cases:
        return special_cases[package]
    # Default: replace hyphens with underscores
    return package.replace("-", "_")


def generate_extras_json(extras: set[str]) -> dict[str, list]:
    """Generate the content for _extras.json."""
    result = {}
    for extra in sorted(extras):
        if extra in EXTRA_METADATA:
            desc, imports = EXTRA_METADATA[extra]
            result[extra] = [desc, imports]
        else:
            # Unknown extra - add a placeholder
            result[extra] = ["TODO: add description", []]
    return result


def check_missing_metadata(extras: set[str]) -> list[str]:
    """Check for extras that don't have metadata defined."""
    return [e for e in extras if e not in EXTRA_METADATA]


def main() -> int:
    """Generate _extras.json from pyproject.toml."""
    extras = get_extras_from_pyproject()

    # Check for missing metadata
    missing = check_missing_metadata(extras)
    if missing:
        print(f"Warning: The following extras need metadata in EXTRA_METADATA: {missing}")
        print("Please update EXTRA_METADATA in scripts/sync_extras.py")

    # Generate the file
    content = generate_extras_json(extras)
    EXTRAS_FILE.write_text(json.dumps(content, indent=2) + "\n")
    print(f"Generated {EXTRAS_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
