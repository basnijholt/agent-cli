---
icon: lucide/mic
---

# transcribe

Transcribe audio from your microphone to text.

## Usage

```bash
agent-cli transcribe [OPTIONS]
```

## Description

This command:

1. Starts listening to your microphone immediately
2. Records your speech
3. When you press `Ctrl+C`, sends audio to a Whisper server
4. Copies the transcribed text to your clipboard
5. Optionally uses an LLM to clean up the transcript

## Examples

```bash
# Basic transcription
agent-cli transcribe --input-device-index 1

# With LLM cleanup
agent-cli transcribe --input-device-index 1 --llm

# List available audio devices
agent-cli transcribe --list-devices

# Transcribe from a saved file
agent-cli transcribe --from-file recording.wav

# Re-transcribe most recent recording
agent-cli transcribe --last-recording 1
```

## Options

### Audio Configuration

| Option | Description |
|--------|-------------|
| `--input-device-index` | Index of the audio input device |
| `--input-device-name` | Device name keywords for partial matching |
| `--list-devices` | List available audio devices and exit |

### Audio Recovery

| Option | Description | Default |
|--------|-------------|---------|
| `--from-file PATH` | Transcribe from a saved WAV file | - |
| `--last-recording N` | Transcribe Nth most recent recording (1=latest) | `0` |
| `--save-recording` / `--no-save-recording` | Save audio for recovery | `true` |

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-provider` | ASR provider: `wyoming`, `openai` | `wyoming` |
| `--llm-provider` | LLM provider: `ollama`, `openai`, `gemini` | `ollama` |

### Wyoming (Local) Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-wyoming-ip` | Wyoming ASR server IP | `localhost` |
| `--asr-wyoming-port` | Wyoming ASR server port | `10300` |

### OpenAI ASR Configuration

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
| `--extra-instructions` | Additional LLM instructions | - |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running background process |
| `--status` | Check if background process is running |
| `--toggle` | Toggle background process on/off |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--clipboard` / `--no-clipboard` | Copy result to clipboard | `true` |
| `--transcription-log PATH` | Log transcriptions with timestamps | - |
| `--log-level` | Set logging level | `WARNING` |
| `--log-file PATH` | Path to a file to write logs to | - |
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

## Workflow Integration

### Toggle Recording Hotkey

The `--toggle` flag is designed for hotkey integration:

```bash
# First press: starts recording
agent-cli transcribe --toggle --input-device-index 1

# Second press: stops recording and transcribes
agent-cli transcribe --toggle
```

### macOS Hotkey (skhd)

```
cmd + shift + r : /path/to/agent-cli transcribe --toggle --input-device-index 1
```

### Transcription Log

Log all transcriptions with timestamps:

```bash
agent-cli transcribe --transcription-log ~/.config/agent-cli/transcriptions.log
```

## Tips

- Use `--list-devices` to find your microphone's index
- Enable `--llm` for cleaner output with proper punctuation
- Use `--last-recording 1` to re-transcribe if you need to adjust settings
