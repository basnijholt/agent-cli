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
| Terminals | 12 | 9 | 2 (iTerm2) | 1 |
| Editors | 10 | 8 | 1 (JetBrains) | 1 |
| Coding Agents | 8 | 3 | 0 | 5 |
| **Total** | **30** | **20** | **3** | **7** |

**Overall: 66.7% verified with primary sources, 10.0% community knowledge, 23.3% unverified.**

### Corrections Made

- **Vim**: Removed incorrect `VIM`/`VIMRUNTIME` detection. These env vars are used BY vim to locate files, NOT to indicate running inside vim. Vim has no integrated terminal.
- **Emacs**: Removed deprecated `EMACS` env var from detection. Only `INSIDE_EMACS` is used (deprecated in Emacs 25 per NEWS.25).
- **Nano**: Added documentation confirming no integrated terminal (terminal-based editor).

---

### Terminal Adapters

| Terminal | Detection | Status | Evidence |
|----------|-----------|--------|----------|
| Tmux | `TMUX` env var | ✅ PASS | `man tmux`: "tmux also initialises the TMUX variable" |
| Tmux | `-c`, `-n` flags | ✅ PASS | `man tmux`: `new-window [-c start-directory] [-n window-name]` |
| Zellij | `ZELLIJ=0` | ✅ PASS | [zellij.dev/documentation/integration.html](https://zellij.dev/documentation/integration.html) |
| Zellij | `--cwd`, `--name` | ✅ PASS | `zellij action new-tab --help` |
| Kitty | `KITTY_WINDOW_ID` | ❌ FAIL | Unverified: test cites `kitten @ launch --help`, which does not document this env var |
| Kitty | `TERM=xterm-kitty` | ✅ PASS | [sw.kovidgoyal.net/kitty/faq](https://sw.kovidgoyal.net/kitty/faq/) |
| Kitty | `--type`, `--cwd`, `--tab-title` | ✅ PASS | `kitten @ launch --help` |
| GNOME Terminal | `GNOME_TERMINAL_SERVICE` | ✅ PASS | Source: [terminal-defines.hh](https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-defines.hh) `#define TERMINAL_ENV_SERVICE_NAME "GNOME_TERMINAL_SERVICE"`, [terminal-screen.cc](https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-screen.cc) sets via `g_hash_table_replace` |
| GNOME Terminal | `--tab`, `--working-directory`, `--title` | ✅ PASS | `gnome-terminal --help-all` |
| iTerm2 | `ITERM_SESSION_ID` | ⚠️ UNDOCUMENTED | Community knowledge - NOT in [official docs](https://iterm2.com/documentation-variables.html), correctly marked |
| iTerm2 | `TERM_PROGRAM=iTerm.app` | ⚠️ UNDOCUMENTED | [Community discussion](https://groups.google.com/g/iterm2-discuss/c/MpOWDIn6QTs) |
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
| JetBrains | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ⚠️ UNDOCUMENTED | [GitHub jediterm#253](https://github.com/JetBrains/jediterm/issues/253) (community knowledge) |
| Zed | `ZED_TERM=true` | ✅ PASS | Source: [terminal.rs](https://github.com/zed-industries/zed/blob/main/crates/terminal/src/terminal.rs) `env.insert("ZED_TERM".to_string(), "true".to_string())` |
| Zed | `TERM_PROGRAM=Zed` | ❌ FAIL | Mentioned in tests without URL/quote; needs PR #14213 link or source snippet |
| Cursor | `CURSOR_AGENT` | ✅ PASS | [cursor.com/docs/agent/terminal](https://cursor.com/docs/agent/terminal) |
| Sublime Text | No integrated terminal | ✅ PASS | [sublimetext.com/docs/command_line.html](https://www.sublimetext.com/docs/command_line.html) - CLI only |

---

### Coding Agent Adapters

| Agent | Detection | Status | Evidence |
|-------|-----------|--------|----------|
| Claude Code | `CLAUDECODE=1` env var | ✅ PASS | Live test: `env \| grep CLAUDE` inside Claude Code session |
| OpenCode | `OPENCODE=1` env var | ✅ PASS | [GitHub PR #1780](https://github.com/sst/opencode/pull/1780) merged 2025-08-11 |
| Cursor Agent | `CURSOR_AGENT` env var | ✅ PASS | [cursor.com/docs/agent/terminal](https://cursor.com/docs/agent/terminal) |
| Aider | Parent process only | ❌ FAIL | No env var - `aider --help` shows only config vars; process-name detection is an implementation decision |
| Codex | Parent process only | ❌ FAIL | No documented env var; process-name detection unverified (install: [npmjs.com/package/@openai/codex](https://www.npmjs.com/package/@openai/codex)) |
| Gemini | Parent process only | ❌ FAIL | No documented env var; process-name detection unverified (install: [npmjs.com/package/@google/gemini-cli](https://www.npmjs.com/package/@google/gemini-cli)) |
| Copilot | Parent process only | ❌ FAIL | No documented env var; process-name detection unverified (install: [npmjs.com/package/@github/copilot](https://www.npmjs.com/package/@github/copilot)) |
| Continue Dev | Parent process only | ❌ FAIL | No documented env var; process-name detection unverified (install: [npmjs.com/package/@continuedev/cli](https://www.npmjs.com/package/@continuedev/cli), command `cn`) |

**Note on Parent Process Detection**: For agents without env vars, we currently detect by checking if any parent process name contains the agent name (e.g., "aider", "codex"). This is an implementation decision (see `tests/dev/test_verification.py::test_parent_process_detection_rationale`), not backed by external evidence of process naming, so treat these detections as ❌ until verified.

---

### Outstanding TODOs

**Terminals:**
- [ ] Kitty: find primary evidence for `KITTY_WINDOW_ID` (docs or source) or remove detection
- [ ] iTerm2: if possible, locate primary docs for `ITERM_SESSION_ID`/`TERM_PROGRAM` (currently community knowledge)

**Editors:**
- [ ] JetBrains: replace GitHub issue evidence with primary docs or keep flagged as community knowledge
- [ ] Zed: add primary evidence for `TERM_PROGRAM=Zed` (PR #14213 link or source snippet)

**Coding Agents:**
- [ ] Parent-process detection (Aider/Codex/Gemini/Copilot/Continue Dev): find external evidence for process names or treat as unverified assumptions
