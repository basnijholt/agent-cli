# Dev Module Verification Checklist

Living document tracking verification status of all dev module features.
Compare our implementation against GTR (CodeRabbit's git-worktree-runner) and real-world testing.

## High-Level Comparison with gtr

Both tools manage git worktrees with editor and AI agent integration. Key differences:

| Aspect | gtr | agent-cli dev |
|--------|-----|---------------|
| Language | Bash (portable, no deps) | Python (part of agent-cli) |
| Installation | `curl` one-liner or Homebrew | `pipx install agent-cli` |
| Invocation | `git gtr new` | `agent-cli dev new` |
| Project setup | Manual hooks (`gtr.hook.postCreate`) | Auto-detects project type |
| Terminal multiplexers | Examples only | Built-in (tmux, zellij, kitty) |
| Agent launching | Runs in current shell | Opens in new terminal tab |
| Tab naming | No | Yes (names tab after agent) |
| Run arbitrary commands | `gtr run` | `dev run` |
| Config management | `gtr config` command | Config file only |
| Worktree cleanup | `gtr clean` | `dev clean` (+ `--merged` for PRs) |

**Choose gtr if**: You want a standalone tool with no dependencies, need hook-based customization, or prefer git subcommand style (`git gtr`).

**Choose agent-cli dev if**: You already use agent-cli, want auto-detected project setup, or need terminal multiplexer integration for launching agents in new tabs.

**Legend:**
- ✅ Verified working
- ⚠️ Needs adjustment
- ❓ Unverified / needs testing
- ❌ Not working / missing
- 🔍 Research needed

---

## AI Coding Agents

### Claude Code

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `claude` | `claude` | ✅ | Verified |
| **Alt commands** | `claude-code` | `claude-code` | ✅ | Verified |
| **Special path** | `~/.claude/local/claude` | `~/.claude/local/claude` | ✅ | Both check this path |
| **Detection env var** | None | `CLAUDECODE=1` | ✅ | **VERIFIED** - Claude Code sets `CLAUDECODE=1` (also `CLAUDE_CODE_ENTRYPOINT`) |
| **Detection process** | N/A | Parent process contains "claude" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && "$claude_cmd" "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install URL** | https://claude.com/claude-code | https://code.claude.com/docs/en/overview | ✅ | Updated 2026-01-10 |

### Codex (OpenAI)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `codex` | `codex` | ✅ | Verified |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | Parent process only | ✅ | **Fixed** - No env var, uses parent process detection |
| **Detection process** | N/A | Parent process contains "codex" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && codex "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install hint** | `npm install -g @openai/codex` | N/A | ✅ | Verified: `npm i -g @openai/codex` |

### Gemini CLI

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `gemini` | `gemini` | ✅ | Verified |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | Parent process only | ✅ | **Fixed** - No env var, uses parent process detection |
| **Detection process** | N/A | Parent process contains "gemini" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && gemini "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install hint** | `npm install -g @google/gemini-cli` | N/A | ✅ | Verified package name |

### Aider

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `aider` | `aider` | ✅ | Verified |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | Parent process only | ✅ | **Fixed** - No env var, uses parent process detection |
| **Detection process** | N/A | Parent process contains "aider" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && aider "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install hint** | `pip install aider-chat` | N/A | ✅ | Verified |
| **Install URL** | https://aider.chat | https://aider.chat | ✅ | |

### GitHub Copilot CLI

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `copilot` | `copilot` | ✅ | Verified |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | Parent process only | ✅ | **Fixed** - No env var, uses parent process detection |
| **Detection process** | N/A | Parent process contains "copilot" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && copilot "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install hint** | `npm install -g @github/copilot` | N/A | ✅ | Verified package name |

### Continue Dev

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cn` | `cn` | ✅ | Verified |
| **Alt commands** | None | `continue` | ✅ | We added alt - reasonable addition |
| **Detection env var** | None | Parent process only | ✅ | **Fixed** - No env var, uses parent process detection |
| **Detection process** | N/A | Parent contains "continue" or "cn" | ✅ | Only reliable detection method |
| **Launch args** | `(cd "$path" && cn "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install URL** | https://continue.dev | https://continue.dev | ✅ | |

### OpenCode

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `opencode` | `opencode` | ✅ | Verified |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `OPENCODE_SESSION` | ✅ | **`OPENCODE=1` EXISTS!** - Update code to use this. |
| **Detection process** | N/A | Parent process contains "opencode" | ✅ | Also works |
| **Launch args** | `(cd "$path" && opencode "$@")` | `[exe]` with `cwd=path` | ✅ | Different approach, same result |
| **Install URL** | https://opencode.ai | https://opencode.ai | ✅ | Verified |

### Cursor Agent

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cursor-agent` or `cursor` | `cursor-agent` | ✅ | Verified |
| **Alt commands** | `cursor` | `cursor` | ✅ | |
| **Detection env var** | None | `CURSOR_AGENT_SESSION` | ✅ | **`CURSOR_AGENT` EXISTS!** - Update code to use this. |
| **Detection process** | N/A | Parent contains "cursor-agent" | ✅ | Also works |
| **Launch logic** | Try `cursor-agent`, then `cursor cli`, then `cursor` | Try `cursor-agent`, else `cursor cli` | ✅ | Minor: 2 vs 3 fallbacks |
| **Install URL** | https://cursor.com | https://cursor.com | ✅ | |

---

## Editors

### VS Code

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `code` | `code` | ✅ | Verified |
| **Alt commands** | `code-insiders` | `code-insiders` | ✅ | |
| **Open syntax** | `code "$path"` | `code <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM=vscode` | ✅ | **Verified via official docs** |
| **Install URL** | https://code.visualstudio.com | https://code.visualstudio.com | ✅ | |

### Cursor (Editor)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cursor` | `cursor` | ✅ | Verified |
| **Open syntax** | `cursor "$path"` | `cursor <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM=cursor` or `CURSOR_AGENT` | ✅ | **Verified** - CURSOR_AGENT for agent mode |
| **Install URL** | https://cursor.com | https://cursor.com | ✅ | |

### Zed

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `zed` | `zed` | ✅ | Verified |
| **Open syntax** | `zed "$path"` | `zed <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM=zed` or `ZED_TERM` | ✅ | **Verified via GitHub PR #14213** - TERM_PROGRAM since v0.145.0 |
| **Install URL** | https://zed.dev | https://zed.dev | ✅ | |

### Neovim

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `nvim` | `nvim` | ✅ | Verified |
| **Alt commands** | None | `neovim` | ✅ | We added, reasonable addition |
| **Open syntax** | `(cd "$path" && nvim .)` | `sh -c 'cd "$path" && nvim .'` | ✅ | **Fixed 2025-01-10** - Now matches GTR pattern |
| **Detection env var** | N/A | `NVIM`, `NVIM_LISTEN_ADDRESS` | ✅ | Standard nvim vars |
| **Install URL** | https://neovim.io | https://neovim.io | ✅ | |

### Vim

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `vim` | `vim` | ✅ | Verified |
| **Alt commands** | None | `vi` | ✅ | Common alias |
| **Open syntax** | `(cd "$path" && vim .)` | `sh -c 'cd "$path" && vim .'` | ✅ | **Fixed 2025-01-10** - Now matches GTR pattern |
| **Detection env var** | N/A | `VIM`, `VIMRUNTIME` | ✅ | Standard vim vars |

### Emacs

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `emacs` | `emacs` | ✅ | Verified |
| **Alt commands** | None | `emacsclient` | ✅ | Faster for running daemon |
| **Open syntax** | `emacs "$path" &` | `sh -c 'emacs "$path" &'` or `emacsclient -n <path>` | ✅ | **Fixed 2025-01-10** - Now runs in background |
| **Detection env var** | N/A | `INSIDE_EMACS`, `EMACS` | ✅ | Standard emacs vars |
| **Background** | Yes (`&`) | Yes (`&`) | ✅ | **Fixed 2025-01-10** |

### Sublime Text

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `subl` | `subl` | ✅ | Verified - official CLI helper |
| **Alt commands** | N/A | `sublime_text`, `sublime` | ✅ | Linux executable name |
| **Open syntax** | `subl "$path"` | `subl <path>` | ✅ | Match |
| **Integrated terminal** | N/A | N/A | ✅ | **No built-in terminal** - packages like Terminus available |
| **Install URL** | https://www.sublimetext.com | https://www.sublimetext.com | ✅ | |

### IntelliJ IDEA

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `idea` | `idea` | ✅ | Verified via JetBrains docs |
| **Open syntax** | `idea "$path"` | `idea <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ | JetBrains terminal |
| **Install hint** | Tools > Create Command-line Launcher | N/A | ✅ | Or use Toolbox App |

### PyCharm

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `pycharm` | `pycharm` | ✅ | Verified via JetBrains docs |
| **Alt commands** | None | `charm` | ✅ | Common alias |
| **Open syntax** | `pycharm "$path"` | `pycharm <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ | Shared with other JetBrains |

### WebStorm

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `webstorm` | `webstorm` | ✅ | Verified via JetBrains docs |
| **Open syntax** | `webstorm "$path"` | `webstorm <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ | Shared with other JetBrains |

### GoLand (Extra - not in GTR)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | N/A | `goland` | ✅ | Verified via JetBrains docs |
| **Open syntax** | N/A | `goland <path>` | ✅ | Standard pattern |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ | Shared with other JetBrains |

### RustRover (Extra - not in GTR)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | N/A | `rustrover` | ✅ | Verified via JetBrains docs |
| **Open syntax** | N/A | `rustrover <path>` | ✅ | Standard pattern |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | ✅ | Shared with other JetBrains |

---

## Terminals (Unique to our implementation)

### tmux

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TMUX` | ✅ | Standard tmux env var (verified via man page) |
| **Availability check** | `which tmux` | ✅ | |
| **New tab command** | `tmux new-window -c <path>` | ✅ | Verified via `man tmux` |
| **New tab with command** | `tmux new-window -c <path> <cmd>` | ✅ | shell-command after options |
| **New pane command** | `tmux split-window -v/-h -c <path>` | ✅ | `-h` horizontal, `-v` vertical |
| **Pane with command** | Appends command to args | ✅ | |
| **Note** | No redundant `cd` | ✅ | **Fixed 2025-01-10** - `-c` sets cwd |

### Zellij

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `ZELLIJ` | ✅ | Verified - presence check (value can be "0") |
| **Availability check** | `which zellij` | ✅ | |
| **New tab command** | `zellij action new-tab --cwd <path>` | ✅ | Verified via `--help` |
| **Send command** | `zellij action write-chars <cmd>` | ✅ | Verified via `--help` |
| **Send enter** | `zellij action write 10` | ✅ | Verified - 10 = newline byte |
| **New pane command** | `zellij action new-pane --direction <dir> --cwd <path>` | ✅ | Verified via `--help` |
| **Pane directions** | down, up, left, right | ✅ | Confirmed in help: "right\|down" |
| **Note** | No redundant `cd` | ✅ | **Fixed 2025-01-10** - `--cwd` sets cwd |

### iTerm2

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TERM_PROGRAM` contains `iterm` or `ITERM_SESSION_ID` | ✅ | Verified via docs |
| **Platform** | macOS only | ✅ | |
| **New tab** | AppleScript `create tab with default profile` | ✅ | Verified via official docs |
| **Run command** | `write text "cd <path> && <cmd>"` | ✅ | Standard iTerm2 pattern |

### Kitty

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `KITTY_WINDOW_ID` or `TERM` contains `kitty` | ✅ | Verified via docs |
| **New tab command** | `kitten @ launch --type=tab --cwd=<path>` | ✅ | Verified via official docs |
| **New window (outside)** | `kitty --directory <path>` | ✅ | For when not inside kitty |
| **With command** | `-- sh -c <cmd>` | ✅ | Standard pattern |

### Warp

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TERM_PROGRAM` contains "warp" | ✅ | Verified |
| **Platform** | macOS only | ✅ | |
| **New tab** | AppleScript with System Events | ✅ | Cmd+T keystroke |
| **Tab naming** | Not supported | ✅ | No API available |

### GNOME Terminal

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `GNOME_TERMINAL_SERVICE` | ✅ | Verified via man page |
| **New tab command** | `gnome-terminal --tab --working-directory=<path>` | ✅ | Verified via man page |
| **Tab title** | `--title <name>` | ✅ | Verified via man page |
| **Run command** | `-- bash -c "<cmd>; exec bash"` | ✅ | Keeps shell open |

---

## Core Worktree Functionality

### Git Operations

| Aspect | Status | Notes |
|--------|--------|-------|
| **Create worktree** | ✅ | `dev new` - creates branch + worktree |
| **List worktrees** | ✅ | `dev list` - shows all worktrees |
| **Remove worktree** | ✅ | `dev rm` - removes worktree + optional branch |
| **Prune worktrees** | ✅ | `dev clean` - runs `git worktree prune` |
| **Run in worktree** | ✅ | `dev run <name> <cmd>` - runs command in worktree |
| **Clean merged PRs** | ✅ | `dev clean --merged` - removes worktrees with merged PRs |
| **Branch from issue** | ❌ | Not implemented (gtr doesn't have this either) |

### Dev Environment Management

| Aspect | Status | Notes |
|--------|--------|-------|
| **Create dev env** | ✅ | `dev new` with `-e` (editor) and `-a` (agent) flags |
| **List dev envs** | ✅ | `dev list` shows all worktrees |
| **Delete dev env** | ✅ | `dev rm` with optional `--delete-branch` |
| **Open in editor** | ✅ | `dev editor <name>` |
| **Start agent** | ✅ | `dev agent <name>` |
| **Get path** | ✅ | `dev path <name>` for shell integration |

### Configuration

| Aspect | Status | Notes |
|--------|--------|-------|
| **Default editor** | ✅ | `[dev] default_editor` in config |
| **Default agent** | ✅ | `[dev] default_agent` in config |
| **Per-agent args** | ✅ | `[dev.agent_args]` in config |
| **Worktree base path** | ✅ | `AGENT_SPACE_DIR` or `GTR_WORKTREES_DIR` env var |
| **Auto project setup** | ✅ | Detects npm/pip/cargo/go and runs install |
| **Copy env files** | ✅ | Copies `.env*` files to new worktrees |

---

## Research Tasks

### Environment Variables to Verify

| Tool | Env Var | Purpose | How to Verify |
|------|---------|---------|---------------|
| Claude Code | `CLAUDE_CODE` | Detection | Run claude, check env |
| Codex | `CODEX_SESSION` | Detection | Run codex, check env |
| Gemini | `GEMINI_CLI` | Detection | Run gemini, check env |
| Aider | `AIDER_*` | Detection | Check aider source/docs |
| Continue | `CONTINUE_*` | Detection | Check continue docs |
| VS Code | `TERM_PROGRAM` | Detection | Open VS Code terminal, echo |
| Cursor | `TERM_PROGRAM` | Detection | Open Cursor terminal, echo |
| Neovim | `NVIM` | Detection | Open :terminal, echo |

### Command Syntax to Verify

| Tool | Command | How to Verify |
|------|---------|---------------|
| tmux new-window | `tmux new-window -c <path>` | Run in tmux session |
| tmux split | `tmux split-window -v -c <path>` | Run in tmux session |
| zellij new-tab | `zellij action new-tab --cwd <path>` | Run in zellij session |
| zellij write | `zellij action write 10` | Run in zellij session |
| kitty launch | `kitten @ launch --type=tab` | Run in kitty |

### Install Commands to Verify

| Tool | Claimed Install | Source |
|------|----------------|--------|
| Codex | `npm install -g @openai/codex` | GTR |
| Gemini | `npm install -g @google/gemini-cli` | GTR |
| Copilot | `npm install -g @github/copilot` | GTR |
| Aider | `pip install aider-chat` | GTR |

---

## Action Items

### High Priority (Code Fixes Needed)
- [x] Verify all AI agent env vars (most are made up) - **DONE 2025-01-10**
- [x] Fix OpenCode detection to use `OPENCODE=1` instead of `OPENCODE_SESSION` - **Already correct**
- [x] Fix Cursor Agent detection to use `CURSOR_AGENT` instead of `CURSOR_AGENT_SESSION` - **Already correct**
- [x] Remove fake env var checks from: Claude, Codex, Gemini, Aider, Copilot, Continue - **Already clean**
- [x] Fix vim/neovim to use `cd + .` pattern like GTR - **DONE 2025-01-10**
- [x] Test tmux commands in real tmux session - **Verified via man page 2025-01-10**
- [x] Test zellij commands in real zellij session - **DONE 2025-01-10**

### Medium Priority
- [x] Add background mode for emacs - **DONE 2025-01-10**
- [x] Verify all JetBrains IDE command names - **Verified via JetBrains docs 2025-01-10**
- [x] Test kitty remote control commands - **Verified via official docs 2025-01-10**
- [x] Test iTerm2 AppleScript - **Verified via official docs 2025-01-10**

### Low Priority
- [x] Add nano support (limited use) - **DONE 2026-01-10**
- [x] Verify install URLs are current - **DONE 2026-01-10** (fixed Claude Code URL)

---

## Verification Log

Record verification results here:

```
2025-01-10: AI Agent Environment Variables Research (8 subagents)
  - Claude Code: NO env var set. Feature request #531 exists but not implemented.
  - Codex: NO env var set. Only CODEX_HOME for config directory.
  - Gemini CLI: NO env var set. Package: @google/gemini-cli confirmed.
  - Aider: NO env var set. Uses AIDER_* for config only.
  - Copilot CLI: NO env var set. Package: @github/copilot confirmed.
  - Continue Dev: NO env var set. CLI command is `cn` confirmed.
  - OpenCode: YES! Sets OPENCODE=1 when running (PR #1780).
  - Cursor Agent: YES! Sets CURSOR_AGENT when running.

  Action: Remove fake env vars from 6 agents, fix OpenCode and Cursor to use real vars.

2025-01-10: Live environment check inside Claude Code
  - Claude Code: ACTUALLY SETS `CLAUDECODE=1` and `CLAUDE_CODE_ENTRYPOINT=cli`!
  - Zellij: Sets `ZELLIJ=0` (presence check, not value check)
  - Verified we're running in Zellij session "charming-lake"

  Action: Fixed Claude Code detection to use CLAUDECODE=1.
```

---

*Last updated: 2025-01-10*
