---
icon: lucide/container
---

# Docker Installation

Universal Docker setup that works on any platform with Docker support.

> [!WARNING]
> **Important Limitations**
>
> - **macOS**: Docker does not support GPU acceleration. For 10x better performance, use [macOS native setup](macos.md)
> - **Linux**: Requires NVIDIA Container Toolkit for GPU acceleration

## Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available for Docker
- 10GB free disk space
- For GPU: NVIDIA Container Toolkit ([installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html))

## Quick Start

1. **Start all services with GPU acceleration:**

   ```bash
   docker compose -f docker/docker-compose.yml --profile cuda up
   ```

   Or for CPU-only:

   ```bash
   docker compose -f docker/docker-compose.yml --profile cpu up
   ```

2. **Check if services are running:**

   ```bash
   docker compose -f docker/docker-compose.yml logs
   ```

3. **Install agent-cli:**

   ```bash
   uv tool install agent-cli -p 3.13
   # or: pip install agent-cli
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## Services Overview

The Docker setup provides:

| Service                 | Image                             | Port        | Purpose                        |
| ----------------------- | --------------------------------- | ----------- | ------------------------------ |
| **whisper**             | agent-cli-whisper (custom)        | 10300/10301 | Speech-to-text (Faster Whisper)|
| **tts**                 | agent-cli-tts (custom)            | 10200/10201 | Text-to-speech (Kokoro/Piper)  |
| **transcribe-proxy** | agent-cli-transcribe-proxy     | 61337       | ASR proxy for iOS/external apps|
| **ollama**              | ollama/ollama                     | 11434       | LLM server                     |
| **openwakeword**        | rhasspy/wyoming-openwakeword      | 10400       | Wake word detection            |

## Configuration

### Environment Variables

```bash
# Whisper ASR
WHISPER_MODEL=large-v3      # Model: tiny, base, small, medium, large-v3
WHISPER_TTL=300             # Seconds before unloading idle model

# TTS
TTS_MODEL=kokoro            # For CUDA: kokoro, For CPU: en_US-lessac-medium
TTS_BACKEND=kokoro          # Backend: kokoro (GPU), piper (CPU)
TTS_TTL=300                 # Seconds before unloading idle model

# Transcription Proxy
PROXY_PORT=61337            # Port for transcription proxy
ASR_PROVIDER=wyoming        # ASR provider: wyoming, openai, gemini
ASR_WYOMING_IP=whisper      # Wyoming server hostname (container name in compose)
ASR_WYOMING_PORT=10300      # Wyoming server port
LLM_PROVIDER=ollama         # LLM provider: ollama, openai, gemini
LLM_OLLAMA_MODEL=gemma3:4b  # Ollama model name
LLM_OLLAMA_HOST=http://ollama:11434  # Ollama server URL (container name)
LLM_OPENAI_MODEL=gpt-4.1-nano  # OpenAI model (if using openai provider)
OPENAI_API_KEY=sk-...       # OpenAI API key (if using openai provider)
```

### GPU Support

The CUDA profile automatically enables GPU for Whisper and TTS. For Ollama GPU support, edit the compose file and uncomment the `deploy` section under the ollama service.

## Managing Services

```bash
# Start services in background
docker compose -f docker/docker-compose.yml --profile cuda up -d

# Stop services
docker compose -f docker/docker-compose.yml --profile cuda down

# View logs
docker compose -f docker/docker-compose.yml logs -f

# Rebuild from source
docker compose -f docker/docker-compose.yml --profile cuda up --build
```

## Data Persistence

Services store data in Docker volumes:

- `agent-cli-whisper-cache` - Whisper models
- `agent-cli-tts-cache` - TTS models and voices
- `agent-cli-ollama-data` - Ollama models
- `agent-cli-openwakeword-data` - Wake word models

## Ports Reference

| Port  | Service             | Protocol |
| ----- | ------------------- | -------- |
| 10200 | TTS                 | Wyoming  |
| 10201 | TTS                 | HTTP API |
| 10300 | Whisper             | Wyoming  |
| 10301 | Whisper             | HTTP API |
| 10400 | OpenWakeWord        | Wyoming  |
| 11434 | Ollama              | HTTP API |
| 61337 | Transcription Proxy | HTTP API |

## Alternative: Native Installation

For better performance, consider platform-specific native installation:

- [macOS Native Setup](macos.md) - Metal GPU acceleration
- [Linux Native Setup](linux.md) - NVIDIA GPU acceleration
