---
icon: lucide/volume-2
---

# speak

Convert text to speech using a local or remote TTS engine.

## Usage

```bash
agent-cli speak [TEXT]
```

## Description

A straightforward text-to-speech utility:

1. Takes text from a command-line argument or your clipboard
2. Sends the text to a TTS server
3. Plays the generated audio through your speakers

## Examples

```bash
# Speak from argument
agent-cli speak "Hello, world!"

# Speak from clipboard
agent-cli speak

# Save to file instead of playing
agent-cli speak "Hello" --save-file hello.wav

# List audio output devices
agent-cli speak --list-devices
```

## Options

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-provider` | TTS provider: `wyoming`, `openai`, `kokoro` | `wyoming` |

### Audio Output

| Option | Description |
|--------|-------------|
| `--output-device-index` | Index of audio output device |
| `--output-device-name` | Device name keywords for matching |
| `--tts-speed` | Speech speed multiplier (1.0 = normal) |
| `--list-devices` | List available audio devices |

### Wyoming (Local) Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-wyoming-ip` | Wyoming TTS server IP | `localhost` |
| `--tts-wyoming-port` | Wyoming TTS server port | `10200` |
| `--tts-wyoming-voice` | Voice name (e.g., 'en_US-lessac-medium') | - |
| `--tts-wyoming-language` | Language (e.g., 'en_US') | - |
| `--tts-wyoming-speaker` | Speaker name for multi-speaker voices | - |

### OpenAI Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-openai-model` | OpenAI TTS model | `tts-1` |
| `--tts-openai-voice` | OpenAI voice | `alloy` |
| `--tts-openai-base-url` | Custom OpenAI-compatible URL | - |

### Kokoro Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--tts-kokoro-model` | Kokoro model | `kokoro` |
| `--tts-kokoro-voice` | Kokoro voice | `af_sky` |
| `--tts-kokoro-host` | Kokoro API URL | `http://localhost:8880/v1` |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running TTS process |
| `--status` | Check if TTS process is running |
| `--toggle` | Toggle TTS process on/off |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--save-file PATH` | Save TTS response audio to WAV file | - |
| `--log-level` | Set logging level | `WARNING` |
| `--log-file PATH` | Path to a file to write logs to | - |
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

## Available Voices

### Wyoming (Piper)

List available voices:

```bash
# Check Piper documentation or run with verbose logging
agent-cli speak --log-level DEBUG "test"
```

Common voices:

- `en_US-lessac-medium` - US English, natural
- `en_GB-alan-medium` - British English
- `de_DE-thorsten-medium` - German

### OpenAI

- `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`

### Kokoro

- `af_sky`, `af_bella`, `am_adam`, and more

## Use Cases

### Read Clipboard Aloud

```bash
agent-cli speak
```

### Speed Up Audio

```bash
agent-cli speak "Long text here" --tts-speed 1.5
```

### Save for Later

```bash
agent-cli speak "Important reminder" --save-file reminder.wav
```
