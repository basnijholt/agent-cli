# macOS Native Installation

Native macOS setup with full Metal GPU acceleration for optimal performance.

> **🍎 Recommended for macOS**
> This setup provides ~10x better performance than Docker by utilizing Metal GPU acceleration.

## Prerequisites

- macOS 12 Monterey or later
- 8GB+ RAM (16GB+ recommended)
- 10GB free disk space
- Homebrew installed

## Quick Start

1. **Run the setup script:**

   ```bash
   scripts/setup-macos.sh
   ```

2. **Start all services:**

   ```bash
   scripts/start-all-services.sh
   ```

3. **Install agent-cli:**

   ```bash
   uv tool install agent-cli
   # or: pip install agent-cli
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## What the Setup Does

The `setup-macos.sh` script:

- ✅ Checks for Homebrew
- ✅ Installs `uv` if needed
- ✅ Installs/checks Ollama (native macOS app)
- ✅ Installs Zellij for session management
- ✅ Prepares Wyoming service runners

## Services Overview

| Service          | Implementation         | Port  | GPU Support          |
| ---------------- | ---------------------- | ----- | -------------------- |
| **Ollama**       | Native macOS app       | 11434 | ✅ Metal GPU         |
| **Whisper**      | Wyoming MLX Whisper    | 10300 | ✅ Apple Silicon MLX |
| **Piper**        | Wyoming Piper (via uv) | 10200 | N/A                  |
| **OpenWakeWord** | Wyoming OpenWakeWord   | 10400 | N/A                  |

> **Note:** Whisper uses [wyoming-mlx-whisper](https://github.com/basnijholt/wyoming-mlx-whisper) with `whisper-large-v3-turbo` for near real-time transcription on Apple Silicon.

## Session Management with Zellij

The setup uses Zellij for managing all services in one session:

### Starting Services

```bash
scripts/start-all-services.sh
```

### Zellij Commands

- `Ctrl-O d` - Detach (services keep running)
- `zellij attach agent-cli` - Reattach to session
- `zellij list-sessions` - List all sessions
- `zellij kill-session agent-cli` - Stop all services
- `Alt + arrow keys` - Navigate between panes
- `Ctrl-Q` - Quit (stops all services)

## Manual Service Management

If you prefer running services individually:

```bash
# Terminal 1: Ollama (native GPU acceleration)
ollama serve

# Terminal 2: Whisper (CPU optimized)
scripts/run-whisper.sh

# Terminal 3: Piper (Apple Silicon compatible)
scripts/run-piper.sh

# Terminal 4: OpenWakeWord (macOS compatible fork)
scripts/run-openwakeword.sh
```

## Why Native Setup?

- **10x faster than Docker** - Full Metal GPU acceleration
- **Better resource usage** - Native integration with macOS
- **Automatic model management** - Services handle downloads

## Troubleshooting

### Permission Checker

If hotkeys aren't working, run the permission diagnostic tool:

```bash
agent-cli install-hotkeys --check
```

This will check all required permissions and provide specific guidance on what needs to be fixed.

### Required Permissions for Hotkeys

The hotkey system requires several macOS permissions to function properly:

#### 1. Accessibility (Required for skhd)

**Location**: System Settings → Privacy & Security → Accessibility

- **skhd** must be listed and enabled
- This allows skhd to capture global keyboard shortcuts

**How to enable**:
1. Open System Settings → Privacy & Security → Accessibility
2. Click the `+` button
3. Navigate to `/opt/homebrew/bin/skhd` (or use `which skhd` to find the path)
4. Ensure the checkbox is enabled
5. If skhd was running, restart it: `skhd --restart-service`

#### 2. Microphone (Required for Transcription)

**Location**: System Settings → Privacy & Security → Microphone

- **Terminal** (or your terminal app) needs microphone access
- **skhd** may also need microphone access

**How to enable**:
1. Open System Settings → Privacy & Security → Microphone
2. Enable access for Terminal.app (and iTerm2 if you use it)
3. If prompted when running transcription, click "Allow"

#### 3. Notifications (Required for Visual Feedback)

**Location**: System Settings → Notifications → terminal-notifier

- **terminal-notifier** must have notifications enabled
- Set alert style to **Alerts** (or **Persistent** on newer macOS) for the "Listening..." indicator to stay visible

**How to enable**:
1. Open System Settings → Notifications
2. Find `terminal-notifier` in the list
3. Enable "Allow Notifications"
4. Set "Alert style" to **Alerts** (this keeps the recording indicator visible)
5. Optionally enable "Allow notifications when mirroring or sharing the display"

#### 4. Local Network (Required for AI Services)

**Location**: System Settings → Privacy & Security → Local Network

- **Terminal** needs local network access to communicate with Ollama, Whisper, etc.
- **skhd** may also need local network access

**How to enable**:
1. Open System Settings → Privacy & Security → Local Network
2. Enable access for Terminal.app
3. If skhd is listed, enable it as well

### Terminal-notifier Popup Issues

- Ensure Settings > Notifications > terminal-notifier > Allow Notifications is enabled.
- For a persistent "Listening…" badge, set the Alert style to **Persistent** (or choose **Alerts** on macOS versions that still offer Alert/Banner). This keeps the recording indicator visible while other notifications still auto-dismiss automatically.

### Ollama Issues

```bash
# Check if Ollama is running
ollama list

# Pull a model manually
ollama pull gemma3:4b

# Check Ollama logs
tail -f ~/.ollama/logs/server.log
```

### Service Port Conflicts

```bash
# Check what's using a port
lsof -i :11434
lsof -i :10300
lsof -i :10200
lsof -i :10400
```

### uv/Python Issues

```bash
# Reinstall uv
brew reinstall uv

# Check uv installation
uv --version
```

### Zellij Issues

```bash
# Kill stuck sessions
zellij kill-all-sessions

# Check session status
zellij list-sessions

# Start without Zellij (manual)
# Run each script in separate terminals
```

### Memory/Performance Issues

- Close other apps to free RAM
- Check Activity Monitor for high CPU/Memory usage
- Services will automatically download required models

## Alternative: Docker

If you prefer Docker despite performance limitations:

- [Docker Setup Guide](docker.md)
- Note: ~10x slower due to no GPU acceleration
