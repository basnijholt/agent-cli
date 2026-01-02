---
icon: lucide/download-cloud
---

# install-services

Install all required AI services.

## Usage

```bash
agent-cli install-services
```

## Description

This command installs the following services required by `agent-cli`:

- **Ollama**: Local LLM server
- **Wyoming Faster Whisper**: Speech-to-text
- **Wyoming Piper**: Text-to-speech
- **Wyoming OpenWakeWord**: Wake word detection

It detects your operating system and runs the appropriate installation script.

## Examples

```bash
agent-cli install-services
```

## Next Steps

After installation, you can:
1. Start the services: `agent-cli start-services`
2. Set up hotkeys: `agent-cli install-hotkeys`
