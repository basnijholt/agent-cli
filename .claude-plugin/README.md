# agent-cli-dev Plugin for Claude Code

This plugin teaches Claude Code how to spawn parallel AI coding agents in isolated git worktrees using `agent-cli dev`.

## What It Does

The plugin provides a skill that enables Claude Code to:

- Create isolated git worktrees for parallel development
- Spawn AI coding agents (Claude, Codex, Gemini, Aider) in separate terminal tabs
- Manage multiple features/tasks simultaneously without branch conflicts
- Automatically set up project dependencies in new worktrees

## Installation

### Install agent-cli

```bash
# Using uv (recommended)
uv tool install agent-cli -p 3.13

# Or run directly without installing
uvx --python 3.13 agent-cli dev new my-feature --agent --prompt "..."
```

### Install the Claude Code plugin

```bash
# From the marketplace
claude plugin marketplace add basnijholt/agent-cli

# Then install
claude plugin install agent-cli@agent-cli-dev
```

## Usage

Once installed, Claude Code can automatically use this skill when you ask to:

- "Work on multiple features in parallel"
- "Spawn agents for auth, payments, and notifications"
- "Create a worktree for this bug fix"
- "Delegate this task to a separate agent"

## Key Commands

```bash
# Create worktree with AI agent
agent-cli dev new my-feature --agent --prompt "Implement the login page"

# Use prompt file for longer tasks
agent-cli dev new my-feature --agent --prompt-file task.md

# Check status of all worktrees
agent-cli dev status

# Clean up merged worktrees
agent-cli dev clean --merged
```

## Documentation

Full documentation: [docs/commands/dev.md](https://github.com/basnijholt/agent-cli/blob/main/docs/commands/dev.md)
