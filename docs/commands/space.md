---
icon: lucide/git-branch
---

# space

Parallel development environment manager using git worktrees.

## Overview

The `space` command helps you work on multiple features simultaneously by creating isolated git worktrees. Each "space" is a separate working directory with its own branch, allowing you to:

- Switch between features without stashing changes
- Run multiple AI coding agents in parallel
- Keep your main branch clean while experimenting

Inspired by [git-worktree-runner (gtr)](https://github.com/CodeRabbitAI/git-worktree-runner).

## Quick Start

```bash
# Create a new space (auto-generates branch name like "clever-fox")
agent-cli space new

# Create a space with a specific branch name
agent-cli space new my-feature

# Create a space and open in editor + start AI agent
agent-cli space new my-feature -e -a

# List all spaces
agent-cli space list

# Remove a space
agent-cli space rm my-feature
```

## Subcommands

### `space new`

Create a new parallel development space.

```bash
agent-cli space new [BRANCH] [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `BRANCH` | Branch name (auto-generated if not provided) |

**Options:**

| Option | Description |
|--------|-------------|
| `--from`, `-f` | Create branch from this ref (default: main/master) |
| `--editor`, `-e` | Open in editor after creation |
| `--agent`, `-a` | Start AI coding agent after creation |
| `--with-editor` | Specific editor (cursor, vscode, zed, etc.) |
| `--with-agent` | Specific agent (claude, codex, gemini, aider) |
| `--no-setup` | Skip automatic project setup (npm install, etc.) |
| `--no-copy` | Skip copying .env files |
| `--no-fetch` | Skip git fetch before creating |

**Examples:**

```bash
# Create space from a specific commit
agent-cli space new hotfix --from v1.2.3

# Create space with Cursor and Claude
agent-cli space new feature --with-editor cursor --with-agent claude

# Quick space with defaults from config
agent-cli space new -e -a
```

### `space list`

List all spaces (worktrees) for the current repository.

```bash
agent-cli space list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--porcelain`, `-p` | Machine-readable output (path + branch) |

### `space rm`

Remove a space (worktree).

```bash
agent-cli space rm NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force`, `-f` | Force removal even with uncommitted changes |
| `--delete-branch`, `-d` | Also delete the branch |

### `space path`

Print the path to a space (for shell integration).

```bash
agent-cli space path NAME
```

**Example:**

```bash
# Navigate to a space
cd "$(agent-cli space path my-feature)"
```

### `space editor`

Open a space in an editor.

```bash
agent-cli space editor NAME [--with-editor EDITOR]
```

### `space agent`

Start an AI coding agent in a space.

```bash
agent-cli space agent NAME [--with-agent AGENT]
```

### `space doctor`

Check system requirements and available integrations.

```bash
agent-cli space doctor
```

Shows available editors, AI agents, and terminals with their detection status.

## Discovery Commands

### `space agents`

List available AI coding agents.

```bash
agent-cli space agents
```

### `space editors`

List available editors.

```bash
agent-cli space editors
```

### `space terminals`

List available terminal multiplexers.

```bash
agent-cli space terminals
```

## Supported Integrations

### AI Coding Agents

| Agent | Command | Detection |
|-------|---------|-----------|
| Claude Code | `claude` | `CLAUDECODE=1` env var |
| OpenAI Codex | `codex` | Parent process detection |
| Google Gemini CLI | `gemini` | Parent process detection |
| Aider | `aider` | Parent process detection |
| GitHub Copilot CLI | `copilot` | Parent process detection |
| Continue Dev | `cn` | Parent process detection |
| OpenCode | `opencode` | `OPENCODE=1` env var |
| Cursor Agent | `cursor-agent` | `CURSOR_AGENT` env var |

### Editors

| Editor | Command | Notes |
|--------|---------|-------|
| Cursor | `cursor` | AI-first editor |
| VS Code | `code` | |
| Zed | `zed` | Fast, modern editor |
| Neovim | `nvim` | Uses `cd && nvim .` pattern |
| Vim | `vim` | Uses `cd && vim .` pattern |
| Emacs | `emacs` | Runs in background |
| Sublime Text | `subl` | |
| IntelliJ IDEA | `idea` | |
| PyCharm | `pycharm` | |
| WebStorm | `webstorm` | |
| GoLand | `goland` | |
| RustRover | `rustrover` | |

### Terminal Multiplexers

| Terminal | Detection | New Tab Command |
|----------|-----------|-----------------|
| tmux | `TMUX` env var | `tmux new-window -c <path>` |
| Zellij | `ZELLIJ` env var | `zellij action new-tab --cwd <path>` |
| Kitty | `KITTY_WINDOW_ID` | `kitten @ launch --type=tab` |
| iTerm2 | `ITERM_SESSION_ID` | AppleScript |

## Configuration

Add defaults to your `~/.config/agent-cli/config.toml`:

```toml
[space]
default_editor = "cursor"
default_agent = "claude"
```

Or per-project in `.agent-cli.toml`:

```toml
[space]
default_editor = "zed"
default_agent = "aider"
```

## Automatic Features

### Project Setup

When creating a new space, automatic setup is performed based on detected project type:

| Project Type | Detection | Setup Command |
|--------------|-----------|---------------|
| Python (uv) | `pyproject.toml` + `uv.lock` | `uv sync` |
| Python (poetry) | `pyproject.toml` + `poetry.lock` | `poetry install` |
| Python (pip) | `requirements.txt` | `pip install -r requirements.txt` |
| Node.js (pnpm) | `pnpm-lock.yaml` | `pnpm install` |
| Node.js (yarn) | `yarn.lock` | `yarn install` |
| Node.js (npm) | `package-lock.json` | `npm install` |
| Rust | `Cargo.toml` | `cargo build` |
| Go | `go.mod` | `go mod download` |

### Environment Files

Files matching these patterns are automatically copied to new spaces:

- `.env*` (e.g., `.env`, `.env.local`, `.env.development`)
- `*.env` (e.g., `local.env`)

Use `--no-copy` to skip this.

### Agent Launch

When launching an AI agent, the space command automatically:

1. Detects if you're in tmux/zellij and opens a new tab there
2. Falls back to supported terminals (kitty, iTerm2)
3. Prints instructions if no terminal is detected

## Shell Integration

Add a function to quickly navigate to spaces:

```bash
# ~/.bashrc or ~/.zshrc
scd() {
    cd "$(agent-cli space path "$1")"
}

# Usage: scd my-feature
```

## Tips

- Use `agent-cli space new` without arguments for quick experimentation
- Run `agent-cli space doctor` to verify your setup
- Combine `-e -a` flags to immediately start coding with AI assistance
- Use `--from` to branch from a specific tag or commit
