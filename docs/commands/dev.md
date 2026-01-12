---
icon: lucide/git-branch
---

# dev

Parallel development environment manager using git worktrees.

## Overview

The `dev` command helps you work on multiple features simultaneously by creating isolated git worktrees. Each dev environment is a separate working directory with its own branch, allowing you to:

- Switch between features without stashing changes
- Run multiple AI coding agents in parallel
- Keep your main branch clean while experimenting

Inspired by [git-worktree-runner (gtr)](https://github.com/CodeRabbitAI/git-worktree-runner).

## Quick Start

```bash
# Create a new dev environment (auto-generates branch name like "clever-fox")
agent-cli dev new

# Create a dev environment with a specific branch name
agent-cli dev new my-feature

# Create a dev environment and open in editor + start AI agent
agent-cli dev new my-feature -e -a

# List all dev environments
agent-cli dev list

# Remove a dev environment
agent-cli dev rm my-feature
```

## Subcommands

### `dev new`

Create a new parallel development environment.

```bash
agent-cli dev new [BRANCH] [OPTIONS]
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
| `--agent-args` | Extra arguments to pass to the agent |
| `--direnv` | Generate .envrc file for direnv (auto-detects venv) |
| `--setup/--no-setup` | Run automatic project setup (default: enabled) |
| `--copy-env/--no-copy-env` | Copy .env files from main repo (default: enabled) |
| `--fetch/--no-fetch` | Git fetch before creating (default: enabled) |

**Examples:**

```bash
# Create dev environment from a specific commit
agent-cli dev new hotfix --from v1.2.3

# Create dev environment with Cursor and Claude
agent-cli dev new feature --with-editor cursor --with-agent claude

# Quick dev environment with defaults from config
agent-cli dev new -e -a
```

### `dev list`

List all dev environments (worktrees) for the current repository.

```bash
agent-cli dev list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--porcelain`, `-p` | Machine-readable output (path + branch) |

### `dev rm`

Remove a dev environment (worktree).

```bash
agent-cli dev rm NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force`, `-f` | Force removal even with uncommitted changes |
| `--delete-branch`, `-d` | Also delete the branch |
| `--yes`, `-y` | Skip confirmation |

### `dev path`

Print the path to a dev environment (for shell integration).

```bash
agent-cli dev path NAME
```

**Example:**

```bash
# Navigate to a dev environment
cd "$(agent-cli dev path my-feature)"
```

### `dev editor`

Open a dev environment in an editor.

```bash
agent-cli dev editor NAME [--with-editor EDITOR]
```

### `dev agent`

Start an AI coding agent in a dev environment.

```bash
agent-cli dev agent NAME [--with-agent AGENT]
```

### `dev run`

Run a command in a dev environment.

```bash
agent-cli dev run NAME COMMAND...
```

**Example:**

```bash
# Run tests in the my-feature worktree
agent-cli dev run my-feature npm test

# Run multiple commands
agent-cli dev run my-feature bash -c "npm install && npm test"
```

### `dev clean`

Clean up stale worktrees and empty directories.

```bash
agent-cli dev clean [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--merged` | Remove worktrees with merged PRs (requires gh CLI) |
| `--dry-run`, `-n` | Show what would be done without doing it |
| `--yes`, `-y` | Skip confirmation |

**Examples:**

```bash
# Prune stale worktrees and remove empty directories
agent-cli dev clean

# Also remove worktrees whose PRs have been merged
agent-cli dev clean --merged

# Preview what would be cleaned
agent-cli dev clean --merged --dry-run
```

### `dev doctor`

Check system requirements and available integrations.

```bash
agent-cli dev doctor
```

Shows available editors, AI agents, and terminals with their detection status.

## Discovery Commands

### `dev agents`

List available AI coding agents.

```bash
agent-cli dev agents
```

### `dev editors`

List available editors.

```bash
agent-cli dev editors
```

### `dev terminals`

List available terminal multiplexers.

```bash
agent-cli dev terminals
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
| Nano | `nano` | Uses `cd && nano .` pattern |
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
| Warp | `TERM_PROGRAM=WarpTerminal` | URI scheme + Launch Configurations |
| GNOME Terminal | `GNOME_TERMINAL_SERVICE` | `gnome-terminal --tab` |

## Configuration

Add defaults to your `~/.config/agent-cli/config.toml`:

```toml
[dev]
# Default flags for 'dev new' command
editor = true          # Always open editor (-e)
agent = true           # Always start agent (-a)
direnv = true          # Always generate .envrc (--direnv)

# Worktree creation behavior
setup = true           # Run project setup (npm install, etc.)
copy_env = true        # Copy .env files from main repo
fetch = true           # Git fetch before creating

# Which editor/agent to use when flags are enabled
default_editor = "cursor"
default_agent = "claude"

# Per-agent arguments (applied automatically when launching agents)
[dev.agent_args]
claude = ["--dangerously-skip-permissions"]
aider = ["--model", "gpt-4o"]
```

Or per-project in `.agent-cli.toml`:

```toml
[dev]
editor = true
agent = true
direnv = true
default_editor = "zed"
default_agent = "aider"

[dev.agent_args]
claude = ["--dangerously-skip-permissions", "--model", "opus"]
```

With this configuration, running `agent-cli dev new` will automatically open the editor, start the agent, and set up direnv.

## Automatic Features

### Project Setup

When creating a new dev environment, automatic setup is performed based on detected project type:

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
| Ruby | `Gemfile` or `Gemfile.lock` | `bundle install` |

### Environment Files

The following files are automatically copied to new dev environments:

- `.env`
- `.env.local`
- `.env.example`
- `.envrc`

Use `--no-copy-env` to skip this.

### Direnv Integration

With `--direnv`, a `.envrc` file is automatically generated based on the detected project type:

| Project Type | Generated .envrc Content |
|--------------|-------------------------|
| Nix (flake.nix) | `use flake` |
| Nix (shell.nix) | `use nix` |
| Python (uv) | `source .venv/bin/activate` |
| Python (poetry) | `source "$(poetry env info --path)/bin/activate"` |
| Python (pip/venv) | `source .venv/bin/activate` (or detected venv path) |
| Node.js (with .nvmrc) | `use node` |
| Go | `layout go` |
| Ruby | `layout ruby` |

Multiple directives can be combined. For example, a Python project with `shell.nix` will get:
```bash
use nix
source .venv/bin/activate
```

The generated `.envrc` is automatically trusted with `direnv allow`.

### Agent Launch

When launching an AI agent, the dev command automatically:

1. Detects if you're in tmux/zellij and opens a new tab there
2. Falls back to supported terminals (kitty, iTerm2)
3. Prints instructions if no terminal is detected

## Shell Integration

Add a function to quickly navigate to dev environments:

```bash
# ~/.bashrc or ~/.zshrc
dcd() {
    cd "$(agent-cli dev path "$1")"
}

# Usage: dcd my-feature
```

## Tips

- Use `agent-cli dev new` without arguments for quick experimentation
- Run `agent-cli dev doctor` to verify your setup
- Combine `-e -a` flags to immediately start coding with AI assistance
- Use `--from` to branch from a specific tag or commit
