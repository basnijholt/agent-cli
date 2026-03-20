"""OpenAI Codex CLI coding agent adapter."""

from __future__ import annotations

from pathlib import Path

from .base import CodingAgent

CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"


def _project_section_header(path: Path) -> str:
    """Build the TOML section header for a trusted Codex project path."""
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    return f'[projects."{escaped}"]'


def _ensure_project_trusted(project_path: Path, config_path: Path | None = None) -> bool:
    """Ensure Codex trusts the launched project path for headless launches.

    Returns True when the config file was modified.
    """
    project_path = project_path.expanduser().resolve()
    config_path = (config_path or CODEX_CONFIG_PATH).expanduser()
    header = _project_section_header(project_path)
    trust_line = 'trust_level = "trusted"'

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f"{header}\n{trust_line}\n", encoding="utf-8")
        return True

    text = config_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    for idx, line in enumerate(lines):
        if line.strip() != header:
            continue

        end = len(lines)
        for j in range(idx + 1, len(lines)):
            if lines[j].strip().startswith("[") and lines[j].strip().endswith("]"):
                end = j
                break

        for j in range(idx + 1, end):
            stripped = lines[j].strip()
            if not stripped.startswith("trust_level"):
                continue
            if stripped == trust_line:
                return False
            msg = (
                f"Codex trust for {project_path} is already configured in {config_path}. "
                "Update that section or disable [dev].auto_trust."
            )
            raise RuntimeError(msg)

        lines.insert(idx + 1, trust_line)
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True

    new_text = text.rstrip("\n")
    if new_text:
        new_text += "\n\n"
    new_text += f"{header}\n{trust_line}\n"
    config_path.write_text(new_text, encoding="utf-8")
    return True


class Codex(CodingAgent):
    """OpenAI Codex CLI coding agent."""

    name = "codex"
    command = "codex"
    install_url = "https://github.com/openai/codex"
    detect_process_name = "codex"

    def prompt_args(self, prompt: str) -> list[str]:
        """Return prompt as positional argument.

        Codex accepts prompt as a positional argument:
        `codex "your prompt here"`

        See: codex --help
        """
        return [prompt]

    def prepare_launch(self, worktree_path: Path, repo_root: Path) -> str | None:  # noqa: ARG002
        """Ensure Codex trusts the repository root before launch."""
        if _ensure_project_trusted(repo_root, CODEX_CONFIG_PATH):
            return f"Trusted {repo_root.resolve()} in Codex config"
        return None
