---
icon: lucide/boxes
---

# Architecture

How Agent CLI works under the hood.

## System Overview

Agent CLI is built around a modular service architecture where different AI capabilities are provided by interchangeable backends.

For usage and flags, see [Commands Reference](../commands/index.md) and [Configuration](../configuration.md).

```
┌────────────────────────────────────────────────────────────────┐
│                          Agent CLI                             │
│  ┌──────────┐ ┌───────────┐ ┌──────┐ ┌───────────┐ ┌────────┐  │
│  │transcribe│ │voice-edit │ │ chat │ │ assistant │ │  ...   │  │
│  └────┬─────┘ └─────┬─────┘ └──┬───┘ └─────┬─────┘ └────────┘  │
└───────┼─────────────┼──────────┼───────────┼───────────────────┘
        │             │          │           │
        ▼             ▼          ▼           ▼
┌────────────────────────────────────────────────────────────────┐
│                     Provider Abstraction                       │
│     ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│     │ ASR Provider│   │ LLM Provider│   │ TTS Provider│        │
│     └──────┬──────┘   └──────┬──────┘   └──────┬──────┘        │
└────────────┼─────────────────┼─────────────────┼───────────────┘
             │                 │                 │
      ┌──────┼──────┐    ┌─────┼─────┐    ┌───────┼───────┐
      ▼      ▼      ▼    ▼     ▼     ▼    ▼   ▼   ▼   ▼   ▼
 ┌───────┐┌──────┐┌──────┐┌──────┐┌──────┐┌─────┐┌──────┐┌──────┐┌──────┐
 │Wyoming││OpenAI││Gemini││Ollama││OpenAI││Piper││OpenAI││Kokoro││Gemini│
 │Whisper││Whispr││ ASR  ││      ││Gemini││     ││ TTS  ││      ││ TTS  │
 └───────┘└──────┘└──────┘└──────┘└──────┘└─────┘└──────┘└──────┘└──────┘
```

## Provider System

Each AI capability (ASR, LLM, TTS) has multiple backend providers:

### ASR (Automatic Speech Recognition)

| Provider | Implementation | GPU Support | Latency |
|----------|---------------|-------------|---------|
| `wyoming` | Wyoming Whisper (faster-whisper/MLX) | CUDA/Metal | Low |
| `openai` | OpenAI-compatible Whisper API | Cloud | Medium |
| `gemini` | Google Gemini API | Cloud | Medium |

### LLM (Large Language Model)

| Provider | Implementation | GPU Support | Privacy |
|----------|---------------|-------------|---------|
| `ollama` | Ollama (local) | CUDA/Metal | Full |
| `openai` | OpenAI-compatible API | Cloud | Partial |
| `gemini` | Google Gemini API | Cloud | Partial |

### TTS (Text-to-Speech)

| Provider | Implementation | Quality | Speed |
|----------|---------------|---------|-------|
| `wyoming` | Wyoming Piper | Good | Fast |
| `openai` | OpenAI-compatible TTS | Excellent | Medium |
| `kokoro` | Kokoro TTS | Good | Fast |
| `gemini` | Google Gemini TTS | Good | Medium |

## Wyoming Protocol

Agent CLI uses the [Wyoming Protocol](https://github.com/rhasspy/wyoming) for local AI services. Wyoming provides a simple TCP-based protocol for:

- Speech-to-text (ASR)
- Text-to-speech (TTS)
- Wake word detection

### Default Ports

| Service | Port | Protocol |
|---------|------|----------|
| Whisper (ASR) | 10300 | Wyoming |
| Piper (TTS) | 10200 | Wyoming |
| OpenWakeWord | 10400 | Wyoming |
| Ollama (LLM) | 11434 | HTTP |
| RAG Proxy | 8000 | HTTP |
| Memory Proxy | 8100 | HTTP |

## Audio Pipeline

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│ Microphone│───▶│sounddevice│───▶│    WAV    │───▶│  Wyoming  │
│           │    │  capture  │    │   buffer  │    │    ASR    │
└───────────┘    └───────────┘    └───────────┘    └─────┬─────┘
                                                         │
                                                         ▼
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  Speakers │◀───│sounddevice│◀───│    WAV    │◀───│  Wyoming  │
│           │    │  playback │    │   buffer  │    │    TTS    │
└───────────┘    └───────────┘    └───────────┘    └───────────┘
```

## Configuration Loading

Configuration is loaded from multiple sources with the following precedence:

1. **Command-line arguments** (highest priority)
2. **Environment variables** (`OPENAI_API_KEY`, etc.)
3. **Config file** (`--config`/`--path`, `$AGENT_CLI_CONFIG_HOME/config.toml`, `./agent-cli-config.toml`, `$XDG_CONFIG_HOME/agent-cli/config.toml`, or `~/.config/agent-cli/config.toml`)
4. **Default values** (lowest priority)

## Process Management

Commands that run as background processes use a PID file system:

```
~/.cache/agent-cli/
├── assistant.pid
├── chat.pid
├── speak.pid
├── transcribe.pid
├── transcribe-live.pid
└── voice-edit.pid

~/.config/agent-cli/
├── config.toml              # Configuration
├── audio/                   # Saved recordings (transcribe-live)
├── history/                 # Chat history
├── transcriptions/          # Saved WAV files
└── transcriptions.jsonl     # Transcription log
```

## Memory System

See [Memory System Architecture](memory.md) for details on the long-term memory implementation.
Usage: [memory command](../commands/memory.md).

## RAG System

See [RAG System Architecture](rag.md) for details on the document retrieval system.
Usage: [rag-proxy command](../commands/rag-proxy.md).

## Dependencies

Agent CLI uses a modular dependency structure. The base package is lightweight, with features installed as optional extras.

### Core Dependencies

Always installed:

- **typer** - CLI framework
- **pydantic** - Data validation
- **rich** - Terminal formatting
- **pyperclip** - Clipboard access
- **httpx** - HTTP client

### Provider Extras

Install with `agent-cli install-extras <name>` or `pip install agent-cli[name]`:

| Extra | Purpose | Key Packages |
|-------|---------|--------------|
| `audio` | Voice features | sounddevice, wyoming, numpy |
| `llm` | AI processing | pydantic-ai-slim (OpenAI, Gemini) |

### Feature Extras

| Extra | Purpose | Key Packages |
|-------|---------|--------------|
| `vad` | Voice activity detection | onnxruntime |
| `rag` | Document chat | chromadb, markitdown |
| `memory` | Long-term memory | chromadb |
| `server` | Local ASR/TTS servers | fastapi |
| `faster-whisper` | Whisper (CUDA/CPU) | faster-whisper |
| `mlx-whisper` | Whisper (Apple Silicon) | mlx-whisper |

See [`install-extras`](../commands/install-extras.md) for the full list and installation instructions.

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| macOS (Apple Silicon) | Full | Metal GPU acceleration |
| macOS (Intel) | Full | CPU-only |
| Linux (x86_64) | Full | NVIDIA GPU support |
| Linux (ARM) | Partial | CPU-only |
| Windows (WSL2) | Full | Via WSL2 |
| Windows (Native) | Experimental | Limited testing |
