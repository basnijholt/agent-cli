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

## Installation Options

### Option 1: Simple Setup with uvx (Recommended)

This is the easiest method, using `uvx` to run services without managing repositories or virtual environments:

```bash
cd scripts
chmod +x setup-macos-simple.sh
./setup-macos-simple.sh
```

Then run all services:
```bash
./start-all-services.sh
```

### Option 2: Full Setup with Repository Clones

For more control and customization:

```bash
cd scripts
chmod +x setup-macos.sh
./setup-macos.sh
```

This will:
- Clone the Wyoming service repositories
- Set up Python virtual environments
- Build Piper from source (if needed)
- Create run scripts for each service

## Running Services

### Using tmux (Recommended)

Both setup options create scripts to run all services in tmux:

```bash
# For simple setup:
./start-all-services.sh

# For full setup:
./start-services-macos.sh
```

tmux commands:
- `Ctrl-B d` - Detach from session
- `tmux attach -t agent-cli-services` - Reattach to session
- `Ctrl-B arrow keys` - Navigate between panes

### Running Services Individually

For simple setup:
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

For full setup:
```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: Whisper
./run-whisper.sh

# Terminal 3: Piper
./run-piper.sh

# Terminal 4: OpenWakeWord
./run-openwakeword.sh
```

## Service Ports

- Ollama: 11434
- Piper (TTS): 10200
- Whisper (STT): 10300
- OpenWakeWord: 10400

## Notes

1. **Ollama**: Uses the official macOS app which provides native GPU acceleration
2. **Whisper**: Wyoming Faster Whisper uses CPU by default, but is optimized for performance
3. **Piper**: May require building from source on Apple Silicon; pre-built binaries are limited
4. **OpenWakeWord**: Runs on CPU, listening for wake words like "ok nabu"

## Troubleshooting

- If services fail to start, check that all dependencies are installed
- Ensure ports are not already in use by other applications
- For Piper on Apple Silicon, you may need to build from source
- Check logs in each tmux pane for service-specific errors
- If using uvx, ensure `uv` is installed: `brew install uv`

## Alternative: Docker

If you prefer consistency across platforms over performance, you can still use Docker with the provided `docker-compose.yml`, but note that GPU acceleration will not be available on macOS.
