---
icon: lucide/play
---

# start-services

Start all agent-cli services in a Zellij session.

## Usage

```bash
agent-cli start-services [OPTIONS]
```

## Description

Starts:

- Ollama (LLM server)
- Wyoming Faster Whisper (speech-to-text)
- Wyoming Piper (text-to-speech)
- Wyoming OpenWakeWord (wake word detection)

Services run inside a Zellij session named `agent-cli`.

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--attach` / `--no-attach` | Attach to the Zellij session after starting | `true` |
| `--help`, `-h` | Show help for the command | - |

## Examples

```bash
# Start services and attach
agent-cli start-services

# Start services without attaching
agent-cli start-services --no-attach
```
