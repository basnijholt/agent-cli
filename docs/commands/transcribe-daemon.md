---
icon: lucide/radio
---

# transcribe-daemon

A continuous background transcription service with voice activity detection (VAD).

## Usage

```bash
agent-cli transcribe-daemon [OPTIONS]
```

## Description

Runs as a daemon, listening to your microphone and automatically segmenting speech using voice activity detection:

1. Starts listening immediately
2. Detects when you start and stop speaking
3. Automatically transcribes each speech segment
4. Logs results with timestamps
5. Optionally saves audio as MP3 files

Press `Ctrl+C` to stop the daemon.

## Installation

Requires the `vad` extra:

```bash
uv tool install "agent-cli[vad]"
# or
pip install "agent-cli[vad]"
```

## Examples

```bash
# Basic daemon
agent-cli transcribe-daemon

# With custom role
agent-cli transcribe-daemon --role meeting

# With LLM cleanup
agent-cli transcribe-daemon --llm

# Custom silence threshold
agent-cli transcribe-daemon --silence-threshold 1.5
```

## Options

### VAD Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `-r`, `--role` | Role name for logging (e.g., 'meeting', 'notes') | `user` |
| `-s`, `--silence-threshold` | Seconds of silence to end a segment | `1.0` |
| `-m`, `--min-segment` | Minimum speech duration in seconds | `0.25` |
| `--vad-threshold` | Speech detection threshold (0.0-1.0) | `0.3` |

### Audio Storage

| Option | Description | Default |
|--------|-------------|---------|
| `--save-audio` / `--no-save-audio` | Save audio segments as MP3 | `true` |
| `--audio-dir PATH` | Directory for MP3 files | `~/.config/agent-cli/audio` |
| `-t`, `--transcription-log PATH` | JSON Lines log file | `~/.config/agent-cli/transcriptions.jsonl` |
| `--clipboard` / `--no-clipboard` | Copy each transcription to clipboard | `false` |

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-provider` | ASR provider: `wyoming`, `openai` | `wyoming` |
| `--llm-provider` | LLM provider: `ollama`, `openai`, `gemini` | `ollama` |

### Audio Input

| Option | Description |
|--------|-------------|
| `--input-device-index` | Index of audio input device |
| `--input-device-name` | Input device name keywords |
| `--list-devices` | List available devices |

### ASR (Wyoming, local)

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-wyoming-ip` | Wyoming ASR server IP | `localhost` |
| `--asr-wyoming-port` | Wyoming ASR server port | `10300` |

### ASR (OpenAI)

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-openai-model` | OpenAI ASR model | `whisper-1` |
| `--asr-openai-base-url` | Custom Whisper server URL | - |
| `--asr-openai-prompt` | Custom prompt to guide transcription | - |

### LLM (Ollama, local)

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-ollama-model` | Ollama model to use | `gemma3:4b` |
| `--llm-ollama-host` | Ollama server URL | `http://localhost:11434` |

### LLM (OpenAI)

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-openai-model` | OpenAI model to use | `gpt-5-mini` |
| `--openai-api-key` | OpenAI API key (or set `OPENAI_API_KEY`) | - |
| `--openai-base-url` | Custom OpenAI-compatible API URL (or set `OPENAI_BASE_URL`) | - |

### LLM (Gemini)

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-gemini-model` | Gemini model to use | `gemini-2.5-flash` |
| `--gemini-api-key` | Gemini API key (or set `GEMINI_API_KEY`) | - |

### LLM Cleanup

| Option | Description | Default |
|--------|-------------|---------|
| `--llm` / `--no-llm` | Use LLM to process transcript | `false` |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running daemon |
| `--status` | Check if daemon is running |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--log-level` | Set logging level | `WARNING` |
| `--log-file PATH` | Path to a file to write logs to | - |
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

## Output Files

### Transcription Log

JSON Lines format at `~/.config/agent-cli/transcriptions.jsonl`:

```json
{"timestamp": "2024-01-15T10:30:45", "role": "user", "text": "Hello world", "audio_file": "..."}
```

### Audio Files

Organized by date at `~/.config/agent-cli/audio/YYYY/MM/DD/*.mp3`

## Use Cases

### Meeting Notes

```bash
agent-cli transcribe-daemon --role meeting --silence-threshold 2.0
```

### Personal Notes

```bash
agent-cli transcribe-daemon --role notes --llm
```

### Background Logging

```bash
agent-cli transcribe-daemon --no-clipboard &
```
