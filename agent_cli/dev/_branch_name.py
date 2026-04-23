"""Branch name generation for dev worktrees."""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from agent_cli.core.utils import err_console

from . import worktree

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

AGENTS: tuple[str, ...] = ("claude", "codex", "gemini")

_ADJECTIVES = [
    "happy",
    "clever",
    "swift",
    "bright",
    "calm",
    "eager",
    "fancy",
    "gentle",
    "jolly",
    "keen",
    "lively",
    "merry",
    "nice",
    "proud",
    "quick",
    "sharp",
    "smart",
    "sunny",
    "witty",
    "zesty",
    "bold",
    "cool",
    "fresh",
    "grand",
]
_NOUNS = [
    "fox",
    "owl",
    "bear",
    "wolf",
    "hawk",
    "lion",
    "tiger",
    "eagle",
    "falcon",
    "otter",
    "panda",
    "raven",
    "shark",
    "whale",
    "zebra",
    "bison",
    "crane",
    "dolphin",
    "gecko",
    "heron",
    "koala",
    "lemur",
    "moose",
    "newt",
    "oriole",
]

_MAX_BRANCH_NAME_LEN = 80
_MAX_BRANCH_TASK_LEN = 1200
_CLAUDE_BRANCH_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "branch": {
                "type": "string",
                "pattern": r"^[a-z0-9][a-z0-9._/-]{1,79}$",
            },
        },
        "required": ["branch"],
        "additionalProperties": False,
    },
    separators=(",", ":"),
)


def _branch_exists_in_repo(repo_root: Path, branch_name: str) -> bool:
    """Check whether a branch already exists locally or on origin."""
    return any(worktree.check_branch_exists(branch_name, repo_root))


def _ensure_unique_branch_name(
    base_name: str,
    existing_branches: set[str] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Add a numeric suffix when a branch name collides."""
    existing = existing_branches or set()

    def is_available(candidate: str) -> bool:
        if candidate in existing:
            return False
        return repo_root is None or not _branch_exists_in_repo(repo_root, candidate)

    if is_available(base_name):
        return base_name

    for i in range(2, 100):
        candidate = f"{base_name}-{i}"
        if is_available(candidate):
            return candidate

    for _ in range(20):
        candidate = f"{base_name}-{random.randint(100, 999)}"  # noqa: S311
        if is_available(candidate):
            return candidate

    # Last resort: large range, unchecked (98 sequential + 20 random exhausted)
    return f"{base_name}-{random.randint(1000, 9999)}"  # noqa: S311


def _parse_json_lines(output: str) -> list[dict[str, object]]:
    """Parse JSONL output and ignore non-JSON lines."""
    parsed: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        try:
            item = json.loads(stripped_line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def _extract_branch_from_claude_output(output: str) -> str | None:
    """Extract branch name from `claude -p --output-format json` output."""
    for event in reversed(_parse_json_lines(output)):
        structured = event.get("structured_output")
        if isinstance(structured, dict):
            branch = structured.get("branch")
            if isinstance(branch, str) and branch.strip():
                return branch
        result = event.get("result")
        if isinstance(result, str) and result.strip():
            return result
    return None


def _extract_branch_from_codex_output(output: str) -> str | None:
    """Extract branch name from `codex exec --json` output."""
    branch: str | None = None
    for event in _parse_json_lines(output):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            branch = text
    return branch


def _extract_branch_from_gemini_output(output: str) -> str | None:
    """Extract branch name from `gemini -p -o json` output."""
    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            response = item.get("response")
            if isinstance(response, str) and response.strip():
                return response
    return None


def _normalize_ai_branch_candidate(candidate: str, repo_root: Path) -> str | None:
    """Normalize model output into a safe branch slug."""
    lines = [line.strip() for line in candidate.replace("`", "").splitlines() if line.strip()]
    if not lines:
        return None

    branch = lines[0].strip().strip("'\"")
    branch = re.sub(r"^(branch|name)\s*:\s*", "", branch, flags=re.IGNORECASE)
    branch = branch.lower()
    branch = re.sub(r"\s+", "-", branch)
    branch = re.sub(r"[^a-z0-9._/-]", "-", branch)
    branch = re.sub(r"/{2,}", "/", branch)
    branch = re.sub(r"-{2,}", "-", branch)
    branch = branch.strip("./-")
    if len(branch) > _MAX_BRANCH_NAME_LEN:
        branch = branch[:_MAX_BRANCH_NAME_LEN].rstrip("./-")
    if not branch:
        return None

    try:
        result = subprocess.run(
            ["git", "check-ref-format", "--branch", branch],  # noqa: S607
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return branch if result.returncode == 0 else None


def _build_branch_naming_prompt(
    repo_root: Path,
    prompt: str | None,
    from_ref: str | None,
) -> str:
    """Build a constrained prompt for branch name generation."""
    task = (prompt or "").strip()
    if not task:
        task = "General maintenance task."
    if len(task) > _MAX_BRANCH_TASK_LEN:
        task = task[:_MAX_BRANCH_TASK_LEN] + "..."

    base_ref = from_ref or "default branch"
    return (
        "Generate exactly one git branch name.\n"
        "Return only the branch name and nothing else.\n"
        "Do not use tools, do not inspect files, and do not ask follow-up questions.\n"
        "Rules:\n"
        "- lowercase ascii only\n"
        "- allowed characters: a-z 0-9 / - _ .\n"
        "- no spaces, no backticks, no explanation\n"
        "- max 80 characters\n"
        f"Repository: {repo_root.name}\n"
        f"Base ref: {base_ref}\n"
        f"Task: {task}\n"
    )


def _generate_branch_name_with_agent(
    agent_name: str,
    repo_root: Path,
    prompt: str | None,
    from_ref: str | None,
    timeout_seconds: float,
) -> str | None:
    """Run a headless agent to generate a branch name."""
    naming_prompt = _build_branch_naming_prompt(repo_root, prompt, from_ref)

    agent_commands: dict[str, tuple[list[str], Callable[[str], str | None]]] = {
        "claude": (
            [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--permission-mode",
                "plan",
                "--no-session-persistence",
                "--json-schema",
                _CLAUDE_BRANCH_SCHEMA,
                naming_prompt,
            ],
            _extract_branch_from_claude_output,
        ),
        "codex": (
            [
                "codex",
                "-a",
                "never",
                "exec",
                "-s",
                "read-only",
                "--json",
                naming_prompt,
            ],
            _extract_branch_from_codex_output,
        ),
        "gemini": (
            ["gemini", "-p", naming_prompt, "-o", "json"],
            _extract_branch_from_gemini_output,
        ),
    }

    entry = agent_commands.get(agent_name)
    if entry is None:
        return None
    command, extractor = entry

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=repo_root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    raw_branch = extractor(result.stdout)
    if not raw_branch:
        return None
    return _normalize_ai_branch_candidate(raw_branch, repo_root)


def generate_ai_branch_name(
    repo_root: Path,
    existing_branches: set[str],
    prompt: str | None,
    from_ref: str | None,
    preferred_agent: str | None,
    timeout_seconds: float,
) -> str | None:
    """Generate an AI branch name, trying available agents in order."""
    if preferred_agent:
        agent = preferred_agent.lower().strip()
        if agent not in AGENTS or shutil.which(agent) is None:
            return None
        agents = [agent]
    else:
        agents = [a for a in AGENTS if shutil.which(a)]

    for agent_name in agents:
        with err_console.status(f"Generating branch name with {agent_name}..."):
            branch = _generate_branch_name_with_agent(
                agent_name,
                repo_root,
                prompt,
                from_ref,
                timeout_seconds,
            )
        if branch:
            return _ensure_unique_branch_name(
                branch,
                existing_branches,
                repo_root=repo_root,
            )

    return None


def generate_random_branch_name(
    existing_branches: set[str] | None = None,
    *,
    repo_root: Path | None = None,
) -> str:
    """Generate a unique random branch name like 'clever-fox'.

    If the name already exists, adds a numeric suffix (clever-fox-2).
    """
    existing = existing_branches or set()
    base = f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"  # noqa: S311
    return _ensure_unique_branch_name(base, existing, repo_root=repo_root)
