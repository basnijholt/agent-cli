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

Like [git-worktree-runner (gtr)](https://github.com/CodeRabbitAI/git-worktree-runner) but with many more QoL features.

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
| `--prompt`, `-p` | Initial prompt to pass to the AI agent |
| `--direnv` | Generate .envrc file for direnv (auto-detects venv) |
| `--setup/--no-setup` | Run automatic project setup (default: enabled) |
| `--copy-env/--no-copy-env` | Copy .env files from main repo (default: enabled) |
| `--fetch/--no-fetch` | Git fetch before creating (default: enabled) |
| `--verbose`, `-v` | Stream live output from all commands (git, setup, direnv) |

**Examples:**

```bash
# Create dev environment from a specific commit
agent-cli dev new hotfix --from v1.2.3

# Create dev environment with Cursor and Claude
agent-cli dev new feature --with-editor cursor --with-agent claude

# Quick dev environment with defaults from config
agent-cli dev new -e -a

# Create dev environment with an initial prompt for the agent
agent-cli dev new fix-bug -a --prompt "Fix the login validation bug in auth.py"
```

### `dev list`

List all dev environments (worktrees) for the current repository.

```bash
agent-cli dev list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--porcelain`, `-p` | Machine-readable output (path + branch) |

### `dev status`

Show status of all dev environments with git status information.

```bash
agent-cli dev status [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--stale-days`, `-s` | Highlight worktrees inactive for N+ days (default: 7) |
| `--porcelain`, `-p` | Machine-readable output |

**Output columns:**

| Column | Description |
|--------|-------------|
| Name | Worktree directory name |
| Branch | Git branch name |
| Changes | File changes: `M` modified, `S` staged, `?` untracked |
| ↑/↓ | Commits ahead (+) / behind (-) upstream |
| Last Commit | Relative time since last commit |

**Examples:**

```bash
# Show status of all worktrees
agent-cli dev status

# Highlight worktrees inactive for 14+ days
agent-cli dev status --stale-days 14

# Machine-readable output for scripting
agent-cli dev status --porcelain
```

**Example output:**

```
                          Dev Environment Status
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Name        ┃ Branch          ┃ Changes ┃ ↑/↓ ┃ Last Commit    ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━━┩
│ main        │ main            │      3M │  —  │ 24 minutes ago │
│ my-feature  │ feat/my-feature │   clean │  —  │ 9 days ago ⚠️   │
└─────────────┴─────────────────┴─────────┴─────┴────────────────┘

2 worktrees · 1 with uncommitted changes · 1 stale (>7 days)
```

**Legend:**
- `M` = Modified files (not staged)
- `S` = Staged files
- `?` = Untracked files
- `+N` = N commits ahead of upstream
- `-N` = N commits behind upstream
- `⚠️` = Stale worktree (inactive for longer than `--stale-days`)

**Porcelain format:**

Tab-separated values: `name`, `branch`, `modified`, `staged`, `untracked`, `ahead`, `behind`, `timestamp`

```bash
$ agent-cli dev status --porcelain
main	main	3	0	0	0	0	1768343512
my-feature	feat/my-feature	0	0	0	0	0	1767544043
```

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
agent-cli dev editor NAME [--editor/-e EDITOR]
```

### `dev agent`

Start an AI coding agent in a dev environment.

```bash
agent-cli dev agent NAME [--agent/-a AGENT] [--agent-args ARGS] [--prompt/-p PROMPT]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--agent`, `-a` | Specific agent (claude, codex, gemini, aider) |
| `--agent-args` | Extra arguments to pass to the agent |
| `--prompt`, `-p` | Initial prompt to pass to the AI agent |

**Examples:**

```bash
# Start Claude in an existing worktree with a prompt
agent-cli dev agent my-feature --prompt "Continue implementing the user settings page"

# Start aider with a specific task
agent-cli dev agent my-feature -a aider --prompt "Add unit tests for the auth module"
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
| `--no-commits` | Remove worktrees with no commits ahead of default branch |
| `--dry-run`, `-n` | Show what would be done without doing it |
| `--yes`, `-y` | Skip confirmation |

**Examples:**

```bash
# Prune stale worktrees and remove empty directories
agent-cli dev clean

# Also remove worktrees whose PRs have been merged
agent-cli dev clean --merged

# Remove worktrees with no commits (abandoned or manually merged branches)
agent-cli dev clean --no-commits

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

### Terminals

| Terminal | Detection | New Tab Command |
|----------|-----------|-----------------|
| tmux | `TMUX` env var | `tmux new-window -c <path>` |
| Zellij | `ZELLIJ` env var | `zellij action new-tab --cwd <path>` |
| Kitty | `KITTY_WINDOW_ID` | `kitten @ launch --type=tab` |
| iTerm2 | `ITERM_SESSION_ID` | AppleScript |
| Terminal.app | `TERM_PROGRAM=Apple_Terminal` | AppleScript + System Events * |
| Warp | `TERM_PROGRAM=WarpTerminal` | URI scheme + Launch Configurations |
| GNOME Terminal | `GNOME_TERMINAL_SERVICE` | `gnome-terminal --tab` |

\* Requires accessibility permissions in System Preferences > Privacy & Security > Accessibility.

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
| Python (uv) | `pyproject.toml` + `uv.lock` | `uv sync --all-extras` |
| Python (unidep) | `requirements.yaml` or `[tool.unidep]` | `unidep install -e . -n <env>` * |
| Python (unidep monorepo) | `requirements.yaml` in subdirs | `unidep install-all -e -n <env>` * |
| Python (poetry) | `pyproject.toml` + `poetry.lock` | `poetry install` |
| Python (pip) | `requirements.txt` | `pip install -r requirements.txt` |
| Node.js (pnpm) | `pnpm-lock.yaml` | `pnpm install` |
| Node.js (yarn) | `yarn.lock` | `yarn install` |
| Node.js (npm) | `package-lock.json` | `npm install` |
| Rust | `Cargo.toml` | `cargo build` |
| Go | `go.mod` | `go mod download` |
| Ruby | `Gemfile` or `Gemfile.lock` | `bundle install` |

\* For unidep projects, if `conda-lock.yml` is present, `-f conda-lock.yml` is also added.

### Git Submodules

Git submodules are automatically initialized and updated when creating a new dev environment:

```bash
git submodule update --init --recursive
```

This ensures all submodule dependencies are available in the worktree.

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
| Python (unidep) | `micromamba activate <dirname>` (with conda fallback) |
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
