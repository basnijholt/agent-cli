---
name: agent-cli-dev
description: Spawns AI coding agents in isolated git worktrees. Use when the user asks to spawn or launch an agent, delegate a task to a separate agent, or parallelize development across features. Only create a worktree without starting an agent if the user explicitly wants setup only.
---

# Parallel Development with agent-cli dev

This skill teaches you how to spawn parallel AI coding agents in isolated git worktrees using the `agent-cli dev` command.

`agent-cli dev` supports two complementary patterns:
- Separate worktrees for isolated implementation/review tasks
- Multiple agents on the same worktree using `dev agent -m tmux` or `--tmux-session`

## Installation

If `agent-cli` is not available, install it first:

```bash
# Install globally
uv tool install agent-cli -p 3.13

# Or run directly without installing
uvx --python 3.13 agent-cli dev new <branch-name> --prompt "..."
```

## When to spawn parallel agents

Spawn separate agents when:
- Multiple independent features/tasks can be worked on in parallel
- Tasks benefit from isolation (separate branches, no conflicts)
- Large refactoring that can be split by module/component
- Test-driven development (one agent for tests, one for implementation)

Do NOT spawn when:
- Tasks are small and sequential
- Tasks have tight dependencies requiring constant coordination
- The overhead of context switching exceeds the benefit

## Core command

For new features (starts from origin/main):
```bash
agent-cli dev new <branch-name> --prompt "Implement the new feature..."
```

For work on current branch (review, test, fix) - use `--from HEAD`:
```bash
agent-cli dev new <branch-name> --from HEAD --prompt "Review/test/fix..."
```

For longer prompts (recommended for multi-line or complex instructions):
```bash
agent-cli dev new <branch-name> --from HEAD --prompt-file path/to/prompt.md
```

This creates:
1. A new git worktree with its own branch
2. Runs project setup (installs dependencies)
3. Saves your prompt to a unique task file in `.claude/` in the worktree (for reference)
4. Opens a new terminal tab with an AI coding agent
5. Passes your prompt to the agent

**Important**: Use `--prompt-file` for prompts longer than a single line. The `--prompt` option passes text through the shell, which can cause issues with special characters (exclamation marks, dollar signs, backticks, quotes) in ZSH and other shells. Using `--prompt-file` avoids all shell quoting issues.

## Automation rule

When an assistant is executing this workflow on the user's behalf, the spawn is not complete unless the agent receives a prompt at launch time.

- Prefer `--prompt-file`; create the prompt file first, then launch the agent
- Use `dev new ... --prompt-file ...` for a new delegated task
- Use `dev agent ... --prompt-file ...` for another agent in an existing worktree
- Do not stop after `dev new ...` alone if the user's intent was to delegate work immediately
- Do not run `dev new ... --start-agent`, `dev new ... --agent <name>`, or `dev agent ... -m tmux` without `--prompt` or `--prompt-file` unless the user explicitly wants an interactive session that they will drive manually

## Writing effective prompts for spawned agents

Spawned agents work in isolation, so prompts must be **self-contained**. Include:

1. **Clear task description**: What to implement/fix/refactor
2. **Relevant context**: File locations, patterns to follow, constraints
3. **Report request**: Ask the agent to write conclusions to `.claude/REPORT.md`

### Using --prompt-file (recommended)

For any prompt longer than a single sentence:

1. Write the prompt to a temporary file (e.g., `.claude/spawn-prompt.md`)
2. Use `--prompt-file` to pass it to the agent
3. The file can be deleted after spawning

Example workflow:
```bash
# 1. Write prompt to file
# 2. Spawn agent with the file
agent-cli dev new my-feature --prompt-file .claude/spawn-prompt.md
# 3. Optionally clean up
rm .claude/spawn-prompt.md
```

### Prompt template

```
<Task description>

Context:
- <Key file locations>
- <Patterns to follow>
- <Constraints or requirements>

When complete, write a summary to .claude/REPORT.md including:
- What you implemented/changed
- Key decisions you made
- Any questions or concerns for review
```

## Checking spawned agent results

After spawning, you can check progress:

```bash
# List all worktrees and their status
agent-cli dev status

# Read an agent's report
agent-cli dev run <branch-name> cat .claude/REPORT.md

# Open the worktree in your editor
agent-cli dev editor <branch-name>
```

## Same-branch multi-agent workflow

Use this when several agents should inspect or validate the same code at once without separate worktrees.

```bash
# Create the worktree once. This step only prepares the shared workspace.
agent-cli dev new review-auth --from HEAD

# Then launch the actual agents with prompts.
agent-cli dev agent review-auth -m tmux --prompt-file .claude/review-security.md
agent-cli dev agent review-auth -m tmux --prompt-file .claude/review-performance.md
agent-cli dev agent review-auth -m tmux --prompt-file .claude/review-tests.md
```

Key rules for same-worktree launches:
- Use `dev agent`, not `dev new`, after the worktree already exists
- Use `dev agent --agent <agent>` to select a specific agent for an existing worktree; `--with-agent` remains a deprecated alias on this subcommand
- Use `-m tmux` for headless or scripted launching; it works even when not already inside tmux
- By default, each explicit tmux launch joins the same deterministic repo-scoped tmux session, so related agents stay grouped together
- Use `--tmux-session <name>` to reuse or create a specific tmux session when you want custom grouping; this also works when already inside tmux and implies `-m tmux`
- tmux session names cannot contain `.` or `:`
- Ask each agent to write to a unique report path such as `.claude/REPORT-security-<run-id>.md` or `.claude/REPORT-tests-<run-id>.md`
- If you rerun the same prompt repeatedly, include a timestamp or other run id in the report filename so later runs do not overwrite earlier ones
- Each agent launch gets its own unique task file in `.claude/` (e.g., `TASK-{timestamp}-{hex}.md`), so parallel launches do not overwrite each other

### Prompt guidance for shared worktrees

When multiple agents share a worktree, explicitly assign both a focus area and a unique report file. If you rerun the same review prompt often, prefer a timestamped filename such as `.claude/REPORT-security-20260319-153045-123.md`.

Prompt pattern:

```text
Review the auth module for security issues only.

When complete, write findings to .claude/REPORT-security-20260319-153045-123.md including:
- Summary
- Issues found with file/line references
- Suggested fixes
```

## Headless/scripted orchestration

For non-interactive contexts (scripts, cron jobs, other assistants), combine `--prompt-file` with `-m tmux`:

```bash
agent-cli dev new validation-a --from HEAD --agent codex -m tmux \
  --prompt-file .claude/validation-a.md
```

This works without an attached terminal. By default, `agent-cli` creates or reuses the repo-scoped tmux session and returns a pane handle plus attach command. Add `--tmux-session validation-batch` if you need a specific shared session name. Launches may also run pre-launch preparation by default; use `--no-hooks` only when you explicitly need to bypass that behavior.

## Cleanup behavior

- `dev rm` and `dev clean` also clean up tmux windows that `agent-cli` tagged for the worktree
- If git worktree removal succeeds but tmux cleanup is partial, the command warns and still removes the worktree

## Example: Multi-feature implementation

If asked to implement auth, payments, and notifications:

```bash
# Spawn three parallel agents
agent-cli dev new auth-feature --prompt "Implement JWT authentication..."
agent-cli dev new payment-integration --prompt "Add Stripe payment processing..."
agent-cli dev new email-notifications --prompt "Implement email notification system..."
```

Each agent works independently in its own branch. Results can be reviewed and merged separately.

## Key options

| Option | Description |
|--------|-------------|
| `--start-agent` | Start the default/auto-detected agent without an initial prompt |
| `--prompt` / `-p` | Initial prompt for the agent (short prompts only) |
| `--prompt-file` / `-P` | Read prompt from file (recommended for longer prompts) |
| `--from` / `-f` | Base ref (default: origin/main). **Use `--from HEAD` when reviewing/testing current branch!** |
| `--agent` | Specific agent (or `auto`): claude, aider, codex, gemini |
| `--agent-args` | Extra arguments for the agent |
| `--tmux-session` | Reuse or create a specific tmux session. Implies tmux launching and overrides the default repo-scoped session |

@examples.md
