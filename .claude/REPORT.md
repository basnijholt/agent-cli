# Summary

Implemented `--tmux-session <name>` for both `agent-cli dev new` and `agent-cli dev agent`.

Key behavior now matches the agreed plan:

- `--tmux-session` is accepted on both commands
- the value is trimmed, empty values are rejected, and the flag implies `--multiplexer tmux`
- launch precedence is:
  - explicit `tmux_session`
  - repo-derived detached tmux session for explicit `-m tmux` outside tmux
  - current tmux session otherwise
- launched tmux windows are tagged with `@agent_cli_worktree=<absolute path>`
- tmux inventory now searches all sessions with `list-windows -a -F ...`
- `dev rm` and `dev clean` now use shared cleanup helpers that remove the git worktree and then kill only the tagged tmux windows for that worktree
- tmux cleanup failures are surfaced as warnings without turning a successful worktree removal into a failure

Additional maintenance:

- updated tmux verification tests to account for the new tagging subprocess call
- added a narrow `psutil` import annotation in `agent_cli/dev/coding_agents/base.py` so `mypy agent_cli/dev/` runs cleanly

# Verification

Passed:

- `./.venv/bin/uv run pytest tests/ -x --no-cov`
- `./.venv/bin/uv run --with mypy mypy agent_cli/dev/`
- targeted `ruff check` on the changed dev/tmux/test files

Repo-wide lint status:

- `./.venv/bin/uv run ruff check .` still fails on pre-existing unrelated `RUF100` findings for unused `# noqa: ASYNC240` directives outside this feature
