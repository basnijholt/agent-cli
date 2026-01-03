---
icon: lucide/download
---

# install-services

Install the local AI services required by agent-cli.

## Usage

```bash
agent-cli install-services [OPTIONS]
```

## Description

Installs the following services (based on your OS):

- Ollama (local LLM server)
- Wyoming Whisper (faster-whisper on Linux/Intel, MLX Whisper on Apple Silicon)
- Wyoming Piper (text-to-speech)
- Wyoming OpenWakeWord (wake word detection)

## Options

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Show help for the command |

## Example

```bash
agent-cli install-services
```
