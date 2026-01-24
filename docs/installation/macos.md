---
icon: lucide/apple
---

# macOS Native Installation

Native macOS setup with full Metal GPU acceleration for optimal performance.

> [!TIP]
> **🍎 Recommended for macOS** — ~10x better performance than Docker via Metal GPU acceleration.

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
   uv tool install agent-cli -p 3.13
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

> [!NOTE]
> Whisper uses [wyoming-mlx-whisper](https://github.com/basnijholt/wyoming-mlx-whisper) with `whisper-large-v3-turbo` for near real-time transcription on Apple Silicon.

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
# Ollama (brew service recommended)
brew services start ollama
# Or run in foreground:
ollama serve

# Whisper (Apple Silicon: launchd service or manual)
launchctl list com.wyoming_mlx_whisper
# Or run in foreground:
scripts/run-whisper.sh

# Piper
scripts/run-piper.sh

# OpenWakeWord
scripts/run-openwakeword.sh
```

Intel Macs: prefer Docker or a Linux-style Wyoming Faster Whisper setup; MLX Whisper is Apple Silicon only.

## Why Native Setup?

- **10x faster than Docker** - Full Metal GPU acceleration
- **Better resource usage** - Native integration with macOS
- **Automatic model management** - Services handle downloads

## Troubleshooting

### Terminal-notifier Popup Issues

- Ensure Settings > Notifications > terminal-notifier > Allow Notifications is enabled.
- For a persistent “Listening…” badge, set the Alert style to **Persistent** (or choose **Alerts** on macOS versions that still offer Alert/Banner). This keeps the recording indicator visible while other notifications still auto-dismiss automatically.

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
