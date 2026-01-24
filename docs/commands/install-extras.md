---
icon: lucide/package-plus
---

# install-extras

Install optional Python dependencies with pinned versions.

## Usage

```bash
agent-cli install-extras [OPTIONS] [EXTRAS]...
```

## Description

Some agent-cli features require additional Python dependencies that are not installed by default. This command installs them with pinned versions from the project's lock file, ensuring reproducible installations.

Available extras:

| Extra | Description |
|-------|-------------|
| `rag` | RAG proxy (ChromaDB, embeddings) |
| `memory` | Long-term memory proxy |
| `vad` | Voice Activity Detection (silero-vad) |
| `whisper` | Local Whisper ASR (faster-whisper) |
| `whisper-mlx` | MLX Whisper for Apple Silicon |
| `tts` | Local Piper TTS |
| `tts-kokoro` | Kokoro neural TTS |
| `server` | FastAPI server components |

## Options

| Option | Description |
|--------|-------------|
| `--list`, `-l` | List available extras |
| `--help`, `-h` | Show help for the command |

## Examples

```bash
# List available extras
agent-cli install-extras --list

# Install a single extra
agent-cli install-extras vad

# Install multiple extras
agent-cli install-extras rag memory vad
```
