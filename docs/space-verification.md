# Space Module Verification Checklist

Living document tracking verification status of all space module features.
Compare our implementation against GTR (CodeRabbit's git-worktree-runner) and real-world testing.

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
| **Command** | `claude` | `claude` | ❓ | |
| **Alt commands** | `claude-code` | `claude-code` | ❓ | |
| **Special path** | `~/.claude/local/claude` | `~/.claude/local/claude` | ❓ | Check if this path exists on real installs |
| **Detection env var** | None | `CLAUDE_CODE` | 🔍 | Does Claude set any env var? |
| **Detection process** | N/A | Parent process contains "claude" | ❓ | |
| **Launch args** | `(cd "$path" && "$claude_cmd" "$@")` | `[exe]` (no cd) | ⚠️ | GTR uses cd, we don't |
| **Install URL** | https://claude.com/claude-code | https://docs.anthropic.com/en/docs/claude-code | 🔍 | Which is correct? |

### Codex (OpenAI)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `codex` | `codex` | ❓ | |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `CODEX_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent process contains "codex" | ❓ | |
| **Launch args** | `(cd "$path" && codex "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install hint** | `npm install -g @openai/codex` | N/A | 🔍 | Verify install method |

### Gemini CLI

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `gemini` | `gemini` | ❓ | |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `GEMINI_CLI` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent process contains "gemini" | ❓ | |
| **Launch args** | `(cd "$path" && gemini "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install hint** | `npm install -g @google/gemini-cli` | N/A | 🔍 | Verify package name |

### Aider

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `aider` | `aider` | ❓ | |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `AIDER_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent process contains "aider" | ❓ | |
| **Launch args** | `(cd "$path" && aider "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install hint** | `pip install aider-chat` | N/A | ❓ | |
| **Install URL** | https://aider.chat | https://aider.chat | ✅ | |

### GitHub Copilot CLI

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `copilot` | `copilot` | ❓ | |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `COPILOT_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent process contains "copilot" | ❓ | |
| **Launch args** | `(cd "$path" && copilot "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install hint** | `npm install -g @github/copilot` | N/A | 🔍 | Verify package name |

### Continue Dev

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cn` | `cn` | ❓ | |
| **Alt commands** | None | `continue` | 🔍 | We added alt, GTR doesn't have |
| **Detection env var** | None | `CONTINUE_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent contains "continue" or "cn" | ❓ | |
| **Launch args** | `(cd "$path" && cn "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install URL** | https://continue.dev | https://continue.dev | ✅ | |

### OpenCode

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `opencode` | `opencode` | ❓ | |
| **Alt commands** | None | None | ✅ | |
| **Detection env var** | None | `OPENCODE_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent process contains "opencode" | ❓ | |
| **Launch args** | `(cd "$path" && opencode "$@")` | `[exe]` | ⚠️ | GTR uses cd |
| **Install URL** | https://opencode.ai | https://opencode.ai | ❓ | Verify URL exists |

### Cursor Agent

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cursor-agent` or `cursor` | `cursor-agent` | ❓ | |
| **Alt commands** | `cursor` | `cursor` | ✅ | |
| **Detection env var** | None | `CURSOR_AGENT_SESSION` | 🔍 | Made up - verify if real |
| **Detection process** | N/A | Parent contains "cursor-agent" | ❓ | |
| **Launch logic** | Try `cursor-agent`, then `cursor cli`, then `cursor` | Try `cursor-agent`, else `cursor cli` | ⚠️ | GTR has 3 fallbacks |
| **Install URL** | https://cursor.com | https://cursor.com | ✅ | |

---

## Editors

### VS Code

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `code` | `code` | ❓ | |
| **Open syntax** | `code "$path"` | `code <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM=vscode` | 🔍 | Verify env var |
| **Install URL** | https://code.visualstudio.com | N/A | 🔍 | Add to our impl |

### Cursor (Editor)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `cursor` | `cursor` | ❓ | |
| **Open syntax** | `cursor "$path"` | `cursor <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM=cursor` | 🔍 | Verify env var |

### Zed

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `zed` | `zed` | ❓ | |
| **Open syntax** | `zed "$path"` | `zed <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERM_PROGRAM` contains "zed" | 🔍 | Verify |

### Neovim

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `nvim` | `nvim` | ❓ | |
| **Alt commands** | None | `neovim` | 🔍 | We added, verify if exists |
| **Open syntax** | `(cd "$path" && nvim .)` | `nvim <path>` | ⚠️ | Different! GTR uses cd + dot |
| **Detection env var** | N/A | `NVIM`, `NVIM_LISTEN_ADDRESS` | 🔍 | Standard nvim vars |
| **Install URL** | https://neovim.io | https://neovim.io | ✅ | |

### Vim

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `vim` | `vim` | ❓ | |
| **Alt commands** | None | `vi` | ✅ | Common alias |
| **Open syntax** | `(cd "$path" && vim .)` | `vim <path>` | ⚠️ | Different! GTR uses cd + dot |
| **Detection env var** | N/A | `VIM`, `VIMRUNTIME` | 🔍 | Standard vim vars |

### Emacs

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `emacs` | `emacs` | ❓ | |
| **Alt commands** | None | `emacsclient` | ✅ | Faster for running daemon |
| **Open syntax** | `emacs "$path" &` | `emacs <path>` or `emacsclient -n <path>` | ⚠️ | GTR runs in background |
| **Detection env var** | N/A | `INSIDE_EMACS`, `EMACS` | 🔍 | Standard emacs vars |
| **Background** | Yes (`&`) | No | ⚠️ | Should we add? |

### Sublime Text

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `subl` | `subl` | ❓ | |
| **Open syntax** | `subl "$path"` | `subl <path>` | ✅ | Match |
| **Install URL** | https://www.sublimetext.com | https://www.sublimetext.com | ✅ | |

### IntelliJ IDEA

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `idea` | `idea` | ❓ | |
| **Open syntax** | `idea "$path"` | `idea <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | 🔍 | JetBrains terminal |
| **Install hint** | Tools > Create Command-line Launcher | N/A | 🔍 | Add to install URL |

### PyCharm

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `pycharm` | `pycharm` | ❓ | |
| **Alt commands** | None | `charm` | 🔍 | Common alias, verify |
| **Open syntax** | `pycharm "$path"` | `pycharm <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | 🔍 | Shared with other JetBrains |

### WebStorm

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | `webstorm` | `webstorm` | ❓ | |
| **Open syntax** | `webstorm "$path"` | `webstorm <path>` | ✅ | Match |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | 🔍 | Shared with other JetBrains |

### GoLand (Extra - not in GTR)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | N/A | `goland` | 🔍 | Verify command name |
| **Open syntax** | N/A | `goland <path>` | 🔍 | |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | 🔍 | |

### RustRover (Extra - not in GTR)

| Aspect | GTR | Ours | Status | Notes |
|--------|-----|------|--------|-------|
| **Command** | N/A | `rustrover` | 🔍 | Verify command name |
| **Open syntax** | N/A | `rustrover <path>` | 🔍 | |
| **Detection env var** | N/A | `TERMINAL_EMULATOR=JetBrains-JediTerm` | 🔍 | |

---

## Terminals (Unique to our implementation)

### tmux

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TMUX` | 🔍 | Standard tmux var |
| **Availability check** | `which tmux` | ❓ | |
| **New tab command** | `tmux new-window -c <path>` | 🔍 | Verify syntax |
| **New tab with command** | `tmux new-window -c <path> <cmd>` | 🔍 | |
| **New pane command** | `tmux split-window -v/-h -c <path>` | 🔍 | |
| **Pane with command** | Appends command to args | 🔍 | |

### Zellij

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `ZELLIJ` | 🔍 | Standard zellij var |
| **Availability check** | `which zellij` | ❓ | |
| **New tab command** | `zellij action new-tab --cwd <path>` | 🔍 | Verify syntax |
| **Send command** | `zellij action write-chars <cmd>` | 🔍 | |
| **Send enter** | `zellij action write 10` | 🔍 | 10 = newline byte |
| **New pane command** | `zellij action new-pane --direction <dir> --cwd <path>` | 🔍 | |
| **Pane directions** | down, up, left, right | 🔍 | |

### iTerm2

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TERM_PROGRAM=iTerm.app` or `ITERM_SESSION_ID` | 🔍 | |
| **Platform** | macOS only | ✅ | |
| **New tab** | AppleScript | 🔍 | Complex, needs testing |
| **New pane** | AppleScript split | 🔍 | |

### Kitty

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TERM=xterm-kitty` or `KITTY_WINDOW_ID` | 🔍 | |
| **New tab command** | `kitten @ launch --type=tab --cwd=<path>` | 🔍 | |
| **New pane command** | `kitten @ launch --type=window --cwd=<path>` | 🔍 | |
| **With command** | `--hold <cmd>` | 🔍 | |

### Warp

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection env var** | `TERM_PROGRAM=WarpTerminal` | 🔍 | |
| **Platform** | macOS only | ✅ | |
| **New tab** | AppleScript | 🔍 | |

### GNOME Terminal

| Aspect | Implementation | Status | Notes |
|--------|---------------|--------|-------|
| **Detection** | Check for gnome-terminal or GNOME_TERMINAL_SCREEN | 🔍 | |
| **New tab command** | `gnome-terminal --tab --working-directory=<path>` | 🔍 | |
| **Fallback** | `xdg-terminal` | 🔍 | |

---

## Core Worktree Functionality

### Git Operations

| Aspect | Status | Notes |
|--------|--------|-------|
| **Create worktree** | ❓ | `git worktree add` |
| **List worktrees** | ❓ | `git worktree list` |
| **Remove worktree** | ❓ | `git worktree remove` |
| **Prune worktrees** | ❓ | `git worktree prune` |
| **Branch from issue** | 🔍 | Parse GitHub/GitLab issue |

### Space Management

| Aspect | Status | Notes |
|--------|--------|-------|
| **Create space** | ❓ | Worktree + editor + agent |
| **List spaces** | ❓ | Show active worktrees |
| **Delete space** | ❓ | Clean up worktree |
| **Switch space** | ❓ | Change to different worktree |

### Configuration

| Aspect | Status | Notes |
|--------|--------|-------|
| **Default editor** | 🔍 | Config file or auto-detect |
| **Default agent** | 🔍 | Config file or auto-detect |
| **Default terminal** | 🔍 | Config file or auto-detect |
| **Worktree base path** | 🔍 | Where to create worktrees |

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

### High Priority
- [ ] Verify all AI agent env vars (most are made up)
- [ ] Fix vim/neovim to use `cd + .` pattern like GTR
- [ ] Test tmux commands in real tmux session
- [ ] Test zellij commands in real zellij session

### Medium Priority
- [ ] Add background mode for emacs
- [ ] Verify all JetBrains IDE command names
- [ ] Test kitty remote control commands
- [ ] Test iTerm2 AppleScript

### Low Priority
- [ ] Add Atom support (deprecated)
- [ ] Add nano support (limited use)
- [ ] Verify install URLs are current

---

## Verification Log

Record verification results here:

```
# Example format:
# 2024-01-10: Verified tmux TMUX env var - confirmed set in tmux sessions
# 2024-01-10: Tested `zellij action new-tab` - works with --cwd flag
```

---

*Last updated: 2025-01-10*
