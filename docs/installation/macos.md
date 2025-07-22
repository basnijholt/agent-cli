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
   chmod +x scripts/setup-macos.sh
   scripts/setup-macos.sh
   ```

2. **Start all services:**
   ```bash
   scripts/start-all-services.sh
   ```

3. **Install agent-cli:**
   ```bash
   uv tools install agent-cli
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

| Service | Implementation | Port | GPU Support |
|---------|---------------|------|-------------|
| **Ollama** | Native macOS app | 11434 | ✅ Metal GPU |
| **Whisper** | Wyoming Faster Whisper | 10300 | 🔧 CPU optimized |
| **Piper** | Wyoming Piper (via uv) | 10200 | N/A |
| **OpenWakeWord** | Wyoming OpenWakeWord | 10400 | N/A |

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
scripts/run-whisper-uvx.sh

# Terminal 3: Piper (Apple Silicon compatible)
scripts/run-piper-uvx.sh

# Terminal 4: OpenWakeWord (macOS compatible fork)
scripts/run-openwakeword-uvx.sh
```

## Performance Advantages

### Ollama (Native vs Docker)
- **Native**: Full Metal GPU acceleration
- **Docker**: CPU-only, ~10x slower
- **Models**: Native can handle larger models efficiently

### Whisper
- **Optimized**: Wyoming Faster Whisper with CPU optimizations
- **Models**: Supports faster-whisper-tiny-int8 for speed

### Piper
- **Apple Silicon**: Uses piper-tts from PyPI via uv
- **Compatibility**: Works natively on M1/M2/M3 chips

## Special macOS Features

### OpenWakeWord Compatibility
- Uses a [custom fork](https://github.com/basnijholt/wyoming-openwakeword/tree/litert) with LiteRT
- Replaces problematic `tflite-runtime` with `ai-edge-litert`
- Full ARM64 macOS support

### Model Storage
- **Ollama**: `~/.ollama/models/`
- **Whisper**: `scripts/whisper-data/`
- **Piper**: `scripts/piper-data/`

## Troubleshooting

### Ollama Issues
```bash
# Check if Ollama is running
ollama list

# Pull a model manually
ollama pull qwen3:4b

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
- **Close other apps** to free RAM
- **Activity Monitor** - check CPU/Memory usage
- **Ollama**: Larger models need more RAM
- **Consider smaller models** like `qwen3:1.5b` for lower-spec Macs

## Optimization Tips

### Ollama Model Selection
```bash
# Smaller models for older Macs
ollama pull qwen3:1.5b

# Larger models for M2/M3 Pro/Max
ollama pull qwen3:7b
```

### Network Configuration
Services bind to `localhost` by default. For network access:
- Ollama: Set `OLLAMA_HOST=0.0.0.0` in environment
- Other services: Modify run scripts to bind to `0.0.0.0`

## Alternative: Docker

If you prefer Docker despite performance limitations:
- [Docker Setup Guide](docker.md)
- Note: ~10x slower due to no GPU acceleration
