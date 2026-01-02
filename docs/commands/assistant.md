---
icon: lucide/bot
---

# assistant

A hands-free voice assistant that activates on a wake word.

## Usage

```bash
agent-cli assistant [OPTIONS]
```

## Description

This agent continuously listens for a wake word (e.g., "Hey Nabu"):

1. Run the command—it starts listening for the wake word
2. Say the wake word to start recording
3. Speak your command or question
4. Say the wake word again to stop recording
5. The agent transcribes, sends to the LLM, and speaks the response
6. Immediately returns to listening for the wake word

## Examples

```bash
# Start with default wake word
agent-cli assistant --input-device-index 1

# With custom wake word
agent-cli assistant --wake-word "hey_jarvis" --input-device-index 1

# With TTS responses
agent-cli assistant --tts --input-device-index 1

# Custom wake word server
agent-cli assistant --wake-server-ip 192.168.1.100 --wake-server-port 10400
```

## Options

### Wake Word Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--wake-word` | Wake word name (e.g., 'ok_nabu', 'hey_jarvis') | `ok_nabu` |
| `--wake-server-ip` | Wyoming wake word server IP | `localhost` |
| `--wake-server-port` | Wyoming wake word server port | `10400` |

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-provider` | ASR provider: `wyoming`, `openai` | `wyoming` |
| `--llm-provider` | LLM provider: `ollama`, `openai`, `gemini` | `ollama` |
| `--tts-provider` | TTS provider: `wyoming`, `openai`, `kokoro` | `wyoming` |

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

### TTS Options (General)

| Option | Description | Default |
|--------|-------------|---------|
| `--tts` / `--no-tts` | Enable text-to-speech responses | `false` |
| `--tts-speed` | Speech speed multiplier | `1.0` |
| `--output-device-index` | Index of audio output device | - |
| `--output-device-name` | Output device name keywords | - |

### TTS (Wyoming, local)

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-wyoming-ip` | Wyoming TTS server IP | `localhost` |
| `--tts-wyoming-port` | Wyoming TTS server port | `10200` |
| `--tts-wyoming-voice` | Voice name for Wyoming TTS | - |
| `--tts-wyoming-language` | Language for Wyoming TTS | - |
| `--tts-wyoming-speaker` | Speaker name for Wyoming TTS voice | - |

### TTS (OpenAI)

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-openai-model` | OpenAI TTS model | `tts-1` |
| `--tts-openai-voice` | OpenAI voice | `alloy` |
| `--tts-openai-base-url` | Custom OpenAI-compatible URL | - |

### TTS (Kokoro)

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-kokoro-model` | Kokoro model | `kokoro` |
| `--tts-kokoro-voice` | Kokoro voice | `af_sky` |
| `--tts-kokoro-host` | Kokoro API URL | `http://localhost:8880/v1` |

### Output Options

| Option | Description | Default |
|--------|-------------|---------|
| `--clipboard` / `--no-clipboard` | Copy result to clipboard | `true` |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running assistant |
| `--status` | Check if assistant is running |
| `--toggle` | Toggle assistant on/off |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--save-file PATH` | Save TTS response audio to WAV file | - |
| `--log-level` | Set logging level | `WARNING` |
| `--log-file PATH` | Path to a file to write logs to | - |
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

## Available Wake Words

The default OpenWakeWord server supports:

- `ok_nabu` (default)
- `hey_jarvis`
- `alexa`
- `hey_mycroft`

Custom wake words can be trained and added to the OpenWakeWord server.

## Interaction Flow

```
┌─────────────────────────────────────────┐
│         Listening for wake word         │
│              "ok_nabu"                  │
└───────────────────┬─────────────────────┘
                    │ Wake word detected
                    ▼
┌─────────────────────────────────────────┐
│            Recording speech             │
│         (speak your question)           │
└───────────────────┬─────────────────────┘
                    │ Wake word again
                    ▼
┌─────────────────────────────────────────┐
│     Transcribe → LLM → TTS (if enabled) │
└───────────────────┬─────────────────────┘
                    │
                    ▼
              Back to listening
```

## Tips

- Speak clearly after the wake word is detected
- Wait for the TTS response to finish before saying the wake word again
- Use `--tts` for a more natural conversation experience
