---
icon: lucide/server
---

# server

Run ASR (Automatic Speech Recognition) and TTS (Text-to-Speech) servers locally with GPU acceleration.

## Usage

```bash
agent-cli server [COMMAND] [OPTIONS]
```

## Available Servers

| Server | Description | Default Port |
|--------|-------------|--------------|
| [whisper](whisper.md) | Local Whisper ASR server with GPU acceleration and TTL-based memory management | 10301 (HTTP), 10300 (Wyoming) |
| [tts](tts.md) | Local TTS server with Kokoro (GPU) or Piper (CPU) backends | 10201 (HTTP), 10200 (Wyoming) |
| [transcribe-proxy](transcribe-proxy.md) | Proxy server that forwards to configured ASR providers | 61337 |

## Quick Start

=== "Whisper (Speech-to-Text)"

    ```bash
    pip install "agent-cli[whisper]"
    agent-cli server whisper
    ```

    Server runs at `http://localhost:10301` with OpenAI-compatible API.

=== "TTS (Text-to-Speech)"

    ```bash
    pip install "agent-cli[tts-kokoro]"
    agent-cli server tts --backend kokoro
    ```

    Server runs at `http://localhost:10201` with OpenAI-compatible API.

=== "Transcription Proxy"

    ```bash
    pip install "agent-cli[server]"
    agent-cli server transcribe-proxy
    ```

    Proxy runs at `http://localhost:61337`, forwarding to your configured ASR provider.

## Why These Servers?

While Faster Whisper, Piper, and Kokoro are all available as standalone servers, agent-cli's implementations offer unique advantages:

1. **Dual-protocol from one server** - Both OpenAI-compatible API and Wyoming protocol run from the same instance. Use the same server for Home Assistant voice pipelines AND your scripts/apps.

2. **TTL-based memory management** - Like [LlamaSwap](https://github.com/mostlygeek/llama-swap), models load on-demand and automatically unload after idle periods. Run voice services 24/7 without permanently consuming RAM/VRAM - memory is freed when you're not actively using speech features.

3. **Multi-platform acceleration** - Whisper automatically uses the optimal backend: [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon for native Metal acceleration, [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) on Linux/CUDA for GPU acceleration.

4. **Unified configuration** - Consistent CLI interface, environment variables, and Docker setup across all services.

## Common Features

All servers share these capabilities:

- **OpenAI-compatible APIs** - Drop-in replacement for OpenAI's audio APIs
- **Wyoming protocol** - Integration with [Home Assistant](https://www.home-assistant.io/) voice services
- **TTL-based memory management** - Models unload after idle periods (default: 5 minutes), freeing RAM/VRAM
- **Health endpoints** - Monitor server status at `/health`
- **Interactive docs** - Explore APIs at `/docs`

## Choosing the Right Server

| Use Case | Recommended |
|----------|-------------|
| Local GPU-accelerated transcription | [whisper](whisper.md) |
| High-quality GPU TTS | [tts](tts.md) `--backend kokoro` |
| CPU-friendly TTS | [tts](tts.md) `--backend piper` |
| Home Assistant voice integration | [whisper](whisper.md) + [tts](tts.md) (both have Wyoming protocol) |
| iOS Shortcuts integration | [transcribe-proxy](transcribe-proxy.md) |
| Forwarding to cloud providers | [transcribe-proxy](transcribe-proxy.md) |
| Privacy-focused (no cloud) | [whisper](whisper.md) + [tts](tts.md) |
| Memory-constrained system | Both servers support TTL unloading; use smaller whisper models or [tts](tts.md) `--backend piper` (CPU-only) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     agent-cli Commands                       │
│  (transcribe, speak, chat, voice-edit, assistant, etc.)     │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Whisper Server │  │   TTS Server    │  │ Transcription   │
│  (ASR)          │  │                 │  │ Proxy           │
│  Port: 10301    │  │  Port: 10201    │  │ Port: 61337     │
│  Wyoming: 10300 │  │  Wyoming: 10200 │  │                 │
└─────────────────┘  └─────────────────┘  └────────┬────────┘
                                                    │
                              ┌─────────────────────┼─────────────────────┐
                              ▼                     ▼                     ▼
                        ┌──────────┐          ┌──────────┐          ┌──────────┐
                        │  Wyoming │          │  OpenAI  │          │  Gemini  │
                        │  (Local) │          │  (Cloud) │          │  (Cloud) │
                        └──────────┘          └──────────┘          └──────────┘
```
