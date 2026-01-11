# Audit Prompt: Verify Evidence for External Library Assumptions

Use this prompt to have an AI agent verify that all assumptions in the `dev` module are backed by hard evidence.

---

## Prompt

You are auditing the `dev` module in this PR. Your task is to verify that every assumption about external tools (terminals, editors, AI agents) is backed by hard evidence.

### Scope

- `agent_cli/dev/` - all adapters for terminals, editors, and coding agents
- `tests/dev/test_verification.py` - verification tests with evidence docstrings

### For each adapter class, verify

1. **Environment variable detection** (e.g., `detect_env_vars`, `detect_term_program`)
   - Is there a test that documents the official source?
   - Does the evidence include: URL, quote/code snippet, verification method?
   - Is the source primary (official docs, man pages, source code) not secondary (blog posts, Stack Overflow)?

2. **Command-line flags** (e.g., `--cwd`, `--name`, `--tab-title`)
   - Was this verified via `--help` output or man pages?
   - Is the exact flag syntax documented?

3. **Install commands** (npm packages, pip packages)
   - Is the package name verified against npmjs.com or pypi.org?
   - Are there any deprecated package names being used?

### Evidence quality criteria

- ✅ Official docs with URL and quote
- ✅ Man page with exact quote
- ✅ Source code with file path and code snippet
- ✅ CLI `--help` output with exact flags shown
- ⚠️ Community knowledge (acceptable if marked as such)
- ❌ "Assumed" or "should work" without verification
- ❌ Secondary sources without primary verification

### Output format

For each adapter, report:

```
[Adapter Name]
- Detection: [env var] → [PASS/FAIL] - [source URL or reason]
- Commands: [flags] → [PASS/FAIL] - [verification method]
- Install: [package] → [PASS/FAIL] - [registry URL]
```

Flag any items marked ⚠️ (undocumented) or ❌ (unverified).

### Files to check

```
agent_cli/dev/terminals/*.py
agent_cli/dev/editors/*.py
agent_cli/dev/coding_agents/*.py
tests/dev/test_verification.py
```

---

## Audit Results (2026-01-11)

### Summary

| Category | Total Claims | PASS | Undocumented | FAIL |
|----------|-------------|------|--------------|------|
| Terminals | 12 | 12 | 0 | 0 |
| Editors | 10 | 10 | 0 | 0 |
| Coding Agents | 8 | 8 | 0 | 0 |
| **Total** | **30** | **30** | **0** | **0** |

**Overall: 100% verified with primary sources.**

### Corrections Made

- **Vim**: Removed incorrect `VIM`/`VIMRUNTIME` detection. These env vars are used BY vim to locate files, NOT to indicate running inside vim. Vim has no integrated terminal.
- **Emacs**: Removed deprecated `EMACS` env var from detection. Only `INSIDE_EMACS` is used (deprecated in Emacs 25 per NEWS.25).
- **Nano**: Added documentation confirming no integrated terminal (terminal-based editor).
- **Neovim**: Removed deprecated `NVIM_LISTEN_ADDRESS` detection; use `$NVIM` only.
- **Continue Dev**: Parent-process detection now keys off the `cn` command name only.

---

### Terminal Adapters

| Terminal | Detection | Status | Evidence |
|----------|-----------|--------|----------|
| Tmux | `TMUX` env var | ✅ PASS | `man tmux`: "tmux also initialises the TMUX variable" |
| Tmux | `-c`, `-n` flags | ✅ PASS | `man tmux`: `new-window [-c start-directory] [-n window-name]` |
| Zellij | `ZELLIJ=0` | ✅ PASS | [zellij.dev/documentation/integration.html](https://zellij.dev/documentation/integration.html) |
| Zellij | `--cwd`, `--name` | ✅ PASS | `zellij action new-tab --help` |
| Kitty | `KITTY_WINDOW_ID` | ✅ PASS | [sw.kovidgoyal.net/kitty/glossary](https://sw.kovidgoyal.net/kitty/glossary/#envvar-KITTY_WINDOW_ID) - "An integer that is the id for the kitty window the program is running in." |
| Kitty | `TERM=xterm-kitty` | ✅ PASS | [sw.kovidgoyal.net/kitty/faq](https://sw.kovidgoyal.net/kitty/faq/) |
| Kitty | `--type`, `--cwd`, `--tab-title` | ✅ PASS | `kitten @ launch --help` |
| GNOME Terminal | `GNOME_TERMINAL_SERVICE` | ✅ PASS | Source: [terminal-defines.hh](https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-defines.hh) `#define TERMINAL_ENV_SERVICE_NAME "GNOME_TERMINAL_SERVICE"`, [terminal-screen.cc](https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-screen.cc) sets via `g_hash_table_replace` |
| GNOME Terminal | `--tab`, `--working-directory`, `--title` | ✅ PASS | `gnome-terminal --help-all` |
| iTerm2 | `ITERM_SESSION_ID` | ✅ PASS | Source: [PTYSession.m](https://github.com/gnachman/iTerm2/blob/master/sources/PTYSession.m) `env[@"ITERM_SESSION_ID"] = itermId;` |
| iTerm2 | `TERM_PROGRAM=iTerm.app` | ✅ PASS | Source: [PTYSession.m](https://github.com/gnachman/iTerm2/blob/master/sources/PTYSession.m) `env[@"TERM_PROGRAM"] = @"iTerm.app";` |
| Warp | `TERM_PROGRAM=WarpTerminal` | ✅ PASS | [docs.warp.dev/terminal/appearance/prompt](https://docs.warp.dev/terminal/appearance/prompt) |

---

### Editor Adapters

| Editor | Detection | Status | Evidence |
|--------|-----------|--------|----------|
| VS Code | `TERM_PROGRAM=vscode` | ✅ PASS | [code.visualstudio.com/docs/terminal/shell-integration](https://code.visualstudio.com/docs/terminal/shell-integration) |
| Neovim | `$NVIM` env var | ✅ PASS | [neovim.io/doc/user/vvars.html](https://neovim.io/doc/user/vvars.html) |
| Vim | No integrated terminal | ✅ PASS | [vimdoc.sourceforge.net](https://vimdoc.sourceforge.net/htmldoc/starting.html) - VIM/VIMRUNTIME are for locating files, NOT detection |
| Nano | No integrated terminal | ✅ PASS | [nano-editor.org](https://www.nano-editor.org) - Terminal-based editor, no shell inside |
| Emacs | `INSIDE_EMACS` only | ✅ PASS | Source: [comint.el](https://github.com/emacs-mirror/emacs/blob/master/lisp/comint.el). Note: `EMACS` env var deprecated in [Emacs 25](https://github.com/emacs-mirror/emacs/blob/master/etc/NEWS.25) |
| JetBrains | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ PASS | Source: [utils.main.kts](https://github.com/JetBrains/intellij-community/blob/master/platform/jewel/scripts/utils.main.kts) `System.getenv("TERMINAL_EMULATOR") == "JetBrains-JediTerm"` |
| Zed | `ZED_TERM=true` | ✅ PASS | Source: [terminal.rs](https://github.com/zed-industries/zed/blob/main/crates/terminal/src/terminal.rs) `env.insert("ZED_TERM".to_string(), "true".to_string())` |
| Zed | `TERM_PROGRAM=zed` | ✅ PASS | Source: [terminal.rs](https://github.com/zed-industries/zed/blob/main/crates/terminal/src/terminal.rs) `env.insert("TERM_PROGRAM".to_string(), "zed".to_string())` |
| Cursor | `CURSOR_AGENT` | ✅ PASS | [cursor.com/docs/agent/terminal](https://cursor.com/docs/agent/terminal) |
| Sublime Text | No integrated terminal | ✅ PASS | [sublimetext.com/docs/command_line.html](https://www.sublimetext.com/docs/command_line.html) - CLI only |

---

### Coding Agent Adapters

| Agent | Detection | Status | Evidence |
|-------|-----------|--------|----------|
| Claude Code | `CLAUDECODE=1` env var; parent process `claude` | ✅ PASS | npm tarball sets `CLAUDECODE:"1"` and registry `bin` defines `claude` ([tarball](https://registry.npmjs.org/@anthropic-ai/claude-code/-/claude-code-2.1.4.tgz), [registry](https://registry.npmjs.org/@anthropic-ai/claude-code/latest)) |
| OpenCode | `OPENCODE=1` env var; parent process `opencode` | ✅ PASS | Env var from [PR #1780](https://github.com/sst/opencode/pull/1780); process name from [npm registry](https://registry.npmjs.org/opencode-ai/latest) `"bin": {"opencode": "bin/opencode"}` |
| Cursor Agent | `CURSOR_AGENT` env var | ✅ PASS | [cursor.com/docs/agent/terminal](https://cursor.com/docs/agent/terminal) |
| Aider | Parent process only | ✅ PASS | Source: [pyproject.toml](https://raw.githubusercontent.com/Aider-AI/aider/main/pyproject.toml) `[project.scripts] aider = "aider.main:main"` |
| Codex | Parent process only | ✅ PASS | Source: [npm registry](https://registry.npmjs.org/@openai/codex/latest) `"bin": {"codex": "bin/codex.js"}` |
| Gemini | Parent process only | ✅ PASS | Source: [npm registry](https://registry.npmjs.org/@google/gemini-cli/latest) `"bin": {"gemini": "dist/index.js"}` |
| Copilot | Parent process only | ✅ PASS | Source: [npm registry](https://registry.npmjs.org/@github/copilot/latest) `"bin": {"copilot": "npm-loader.js"}` |
| Continue Dev | Parent process only | ✅ PASS | Source: [npm registry](https://registry.npmjs.org/@continuedev/cli/latest) `"bin": {"cn": "dist/cn.js"}` |

**Note on Parent Process Detection**: We use `psutil.Process.name()` to inspect parent process names and compare them to official CLI command names from package metadata (see `tests/dev/test_verification.py::test_parent_process_detection_rationale`).

---

### Resolved TODOs

**Terminals:**
- [x] Kitty: evidence for `KITTY_WINDOW_ID` in kitty glossary
- [x] iTerm2: source code evidence for `ITERM_SESSION_ID` and `TERM_PROGRAM`

**Editors:**
- [x] JetBrains: source code evidence in IntelliJ Community scripts
- [x] Zed: source code evidence for `TERM_PROGRAM=zed`

**Coding Agents:**
- [x] Parent-process detection: CLI command names from package metadata + psutil docs
