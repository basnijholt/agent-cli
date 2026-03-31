# AGENTCLI-001 Report

- Fixed `agent_cli/dev/terminals/tmux.py` so `list_windows_for_worktree()` treats tmux's "no server running" and "no current client" errors as an empty inventory instead of a cleanup warning.
- Added a regression test covering the no-server tmux case in `tests/dev/test_terminals.py`.
- Tightened `agent_cli/dev/cli.py` session normalization to reject tmux session names containing `.` or `:`.
- Added CLI tests covering illegal tmux session names for both `dev new` and `dev agent` in `tests/dev/test_cli.py`.

Verification:

- `env -u VIRTUAL_ENV .venv/bin/uv run pytest tests/ -x --no-cov`
- `env -u VIRTUAL_ENV .venv/bin/uv run ruff check agent_cli/dev/ tests/dev/`
- `env -u VIRTUAL_ENV .venv/bin/uv run --with mypy mypy agent_cli/dev/`
