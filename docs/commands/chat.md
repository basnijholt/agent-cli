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

### Audio Configuration

| Option | Description |
|--------|-------------|
| `--input-device-index` | Index of audio input device |
| `--input-device-name` | Input device name keywords |
| `--output-device-index` | Index of audio output device |
| `--output-device-name` | Output device name keywords |
| `--list-devices` | List available devices |

### TTS Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tts` / `--no-tts` | Enable text-to-speech responses | `false` |
| `--tts-speed` | Speech speed multiplier | `1.0` |
| `--save-file PATH` | Save TTS audio to file | - |

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
