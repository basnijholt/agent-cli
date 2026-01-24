---
icon: lucide/terminal
---

# Commands Reference

Agent CLI provides multiple commands, each designed for a specific purpose.

## Voice & Audio Commands

| Command | Purpose | Use Case |
|---------|---------|----------|
| [`transcribe`](transcribe.md) | Speech-to-text | Record voice → get text in clipboard |
| [`transcribe-daemon`](transcribe-daemon.md) | Continuous transcription | Background service with VAD |
| [`speak`](speak.md) | Text-to-speech | Read text aloud |
| [`voice-edit`](voice-edit.md) | Voice-powered editor | Edit clipboard text with voice commands |
| [`assistant`](assistant.md) | Wake word assistant | Hands-free voice interaction |
| [`chat`](chat.md) | Conversational AI | Full-featured voice chat with tools |

## Text Processing Commands

| Command | Purpose | Use Case |
|---------|---------|----------|
| [`autocorrect`](autocorrect.md) | Grammar & spelling | Fix text from clipboard |

## AI Services Commands

| Command | Purpose | Use Case |
|---------|---------|----------|
| [`rag-proxy`](rag-proxy.md) | RAG server | Chat with your documents |
| [`memory`](memory.md) | Long-term memory | Persistent conversation memory |
| [`server`](server/index.md) | ASR & TTS servers | Local Whisper and Kokoro/Piper with TTL-based memory management |

The [`server`](server/index.md) command provides local ASR (speech-to-text) and TTS (text-to-speech) servers with unique advantages over standalone alternatives:

- **Dual-protocol** - Both OpenAI-compatible API and Wyoming protocol from the same server
- **TTL-based memory management** - Models load on-demand and unload after idle periods, freeing RAM/VRAM
- **Multi-platform acceleration** - MLX Whisper on Apple Silicon, Faster Whisper on Linux/CUDA
- **Unified configuration** - Consistent CLI, environment variables, and Docker setup

## Installation Commands

These commands help set up Agent CLI and its services:

| Command | Purpose |
|---------|---------|
| [`install-services`](install-services.md) | Install all AI services (Ollama, Whisper, Piper, OpenWakeWord) |
| [`install-hotkeys`](install-hotkeys.md) | Set up system-wide hotkeys |
| [`install-extras`](install-extras.md) | Install optional Python dependencies (rag, memory, vad, etc.) |
| [`start-services`](start-services.md) | Start all services in a Zellij terminal session |

## Development Commands

| Command | Purpose | Use Case |
|---------|---------|----------|
| [`dev`](dev.md) | Git worktree manager | Parallel development with AI agents |

## Configuration Commands

| Command | Purpose |
|---------|---------|
| [`config`](config.md) | Manage configuration (init, show, edit) |

## Related

- [Configuration](../configuration.md) - Config file keys and defaults
- [Architecture](../architecture/index.md) - How the system fits together

## Common Options

Most commands support these options (audio/text agents and servers). Installation
and config commands have their own flags. Use `agent-cli <command> --help` to
see the exact options.

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Show help for the command |
| `--config PATH` | Use a specific config file |
| `--log-level LEVEL` | Set logging level (DEBUG, INFO, WARNING, ERROR) |
| `--log-file PATH` | Write logs to a file |
| `--quiet`, `-q` | Suppress console output |
| `--print-args` | Show resolved arguments including config values |

## Provider Options

Most commands support multiple providers:

### LLM Providers (`--llm-provider`)

- `ollama` - Local LLM via Ollama (default)
- `openai` - OpenAI-compatible API
- `gemini` - Google Gemini API

### ASR Providers (`--asr-provider`)

- `wyoming` - Local Whisper via Wyoming (default)
- `openai` - OpenAI-compatible Whisper API
- `gemini` - Google Gemini API

### TTS Providers (`--tts-provider`)

- `wyoming` - Local TTS via Wyoming protocol (Kokoro or Piper, default)
- `openai` - OpenAI-compatible TTS API
- `kokoro` - Local Kokoro TTS (direct, without Wyoming)
- `gemini` - Google Gemini TTS API

## Process Management

Commands with background capabilities support:

| Option | Description |
|--------|-------------|
| `--stop` | Stop a running background process |
| `--status` | Check if a background process is running |
| `--toggle` | Toggle the background process on/off |

Example:

```bash
# Start transcription in background
agent-cli transcribe &

# Check status
agent-cli transcribe --status

# Stop it
agent-cli transcribe --stop
```
