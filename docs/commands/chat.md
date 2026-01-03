---
icon: lucide/message-circle
---

# chat

A full-featured conversational AI assistant with tool-calling capabilities.

## Usage

```bash
agent-cli chat [OPTIONS]
```

## Description

A persistent, conversational agent that you can have a back-and-forth conversation with:

1. Run the command—it starts listening for your voice
2. Speak your command or question
3. The agent transcribes, sends to the LLM (which can use tools), and responds
4. The response is spoken back to you (if TTS enabled)
5. Immediately starts listening for your next command
6. Conversation history is saved between sessions

## Interaction Controls

- **To Interrupt**: Press `Ctrl+C` **once** to stop listening or speaking and return to a listening state
- **To Exit**: Press `Ctrl+C` **twice in a row** to terminate the application

## Examples

```bash
# Start with TTS
agent-cli chat --input-device-index 1 --tts

# List available devices
agent-cli chat --list-devices

# Custom history settings
agent-cli chat --last-n-messages 100 --history-dir ~/.my-chat-history
```

## Options

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

### History Options

| Option | Description | Default |
|--------|-------------|---------|
| `--history-dir PATH` | Directory for conversation history | `~/.config/agent-cli/history` |
| `--last-n-messages N` | Number of messages to include (0 = disable) | `50` |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running chat |
| `--status` | Check if chat is running |
| `--toggle` | Toggle chat on/off |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--save-file PATH` | Save TTS audio to WAV file | - |
| `--log-level` | Set logging level | `WARNING` |
| `--log-file PATH` | Path to a file to write logs to | - |
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

## Available Tools

The chat agent has access to tools that let it interact with your system:

> [!NOTE]
> The memory tools below use a simple, built-in JSON storage system.
> For the advanced, vector-backed memory system, see the [`memory`](memory.md) command.

- **read_file**: Read file contents
- **execute_code**: Run shell commands
- **duckduckgo_search**: Search the web via DuckDuckGo
- **add_memory**: Store information for future conversations
- **search_memory**: Search stored memories
- **update_memory**: Update existing memories
- **list_all_memories**: List all stored memories
- **list_memory_categories**: Show memory category summary

## Example Conversation

```
You: "Read the pyproject.toml file and tell me the project version."
AI: (Uses read_file tool) "The project version is 0.5.0."

You: "What dependencies does it have?"
AI: "The project has the following dependencies: typer, pydantic, ..."

You: "Thanks!"
AI: "You're welcome! Let me know if you need anything else."
```

## Conversation History

History is stored in `~/.config/agent-cli/history/` and persists between sessions.

To start fresh:

```bash
rm -rf ~/.config/agent-cli/history/*
```

Or limit context:

```bash
agent-cli chat --last-n-messages 10
```
