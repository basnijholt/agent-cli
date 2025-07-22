# macOS Setup for Agent CLI Services

This guide provides instructions for setting up the required services on macOS without Docker, enabling GPU acceleration and better performance.

## Prerequisites

- macOS 12 Monterey or later (for Ollama)
- Homebrew installed
- Python 3.8 or later

## Services

The following services are set up:

1. **Ollama** - LLM server
2. **Whisper** - Speech-to-text (Wyoming Faster Whisper)
3. **Piper** - Text-to-speech (Wyoming Piper)
4. **OpenWakeWord** - Wake word detection (Wyoming OpenWakeWord)

## Installation

Run the setup script to install dependencies:

```bash
cd scripts
chmod +x setup-macos.sh
./setup-macos.sh
```

This will:
- Check for Homebrew
- Install `uv` if needed
- Install/check Ollama
- Install Zellij for session management

Then run all services:
```bash
./start-all-services.sh
```

## Running Services

### Using Zellij (Recommended)

Run all services in a Zellij session:

```bash
./start-all-services.sh
```

Zellij commands:
- `Ctrl-O d` - Detach from session (keeps services running)
- `zellij attach agent-cli` - Reattach to session
- `zellij list-sessions` - List all sessions
- `zellij kill-session agent-cli` - Stop all services and kill session
- `Alt + arrow keys` - Navigate between panes
- `Ctrl-P` - Enter pane mode for resizing
- `Ctrl-T` - Create new tab
- `Ctrl-Q` - Quit Zellij (stops all services)

### Running Services Individually

You can also run each service in separate terminals:

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: Whisper
./run-whisper-uvx.sh

# Terminal 3: Piper
./run-piper-uvx.sh

# Terminal 4: OpenWakeWord
./run-openwakeword-uvx.sh
```

## Service Ports

- Ollama: 11434
- Piper (TTS): 10200
- Whisper (STT): 10300
- OpenWakeWord: 10400

## Notes

1. **Ollama**: Uses the official macOS app which provides native GPU acceleration
2. **Whisper**: Wyoming Faster Whisper uses CPU by default, but is optimized for performance
3. **Piper**: Uses piper-tts from PyPI via UV (works on Apple Silicon)
4. **OpenWakeWord**: Works on macOS using the LiteRT fork (automatically used by the scripts)

## Troubleshooting

- If services fail to start, check that all dependencies are installed
- Ensure ports are not already in use by other applications
- For Piper on Apple Silicon, the setup now uses piper-tts from PyPI via UV
- Check logs in each Zellij pane for service-specific errors
- If using uvx, ensure `uv` is installed: `brew install uv`

### OpenWakeWord on macOS

OpenWakeWord now works on macOS! We're using a fork that replaces `tflite-runtime` with LiteRT (ai-edge-litert):
- Fork: https://github.com/basnijholt/wyoming-openwakeword/tree/litert
- PR: https://github.com/rhasspy/wyoming-openwakeword/pull/XXX (pending)
- Uses `ai-edge-litert==1.3.0` which provides cross-platform support including macOS ARM64
- LiteRT is the official replacement for TensorFlow Lite

The run-openwakeword-uvx.sh script automatically uses this fork until the PR is merged.

## Alternative: Docker

If you prefer consistency across platforms over performance, you can still use Docker with the provided `docker-compose.yml`, but note that GPU acceleration will not be available on macOS.
