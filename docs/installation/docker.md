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
   docker compose -f docker/docker-compose.services.yml --profile cuda up
   ```

   Or for CPU-only:

   ```bash
   docker compose -f docker/docker-compose.services.yml --profile cpu up
   ```

2. **Check if services are running:**

   ```bash
   docker compose -f docker/docker-compose.services.yml logs
   ```

3. **Install agent-cli:**

   ```bash
   uv tool install agent-cli
   # or: pip install agent-cli
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## Services Overview

The Docker setup provides:

| Service          | Image                             | Port        | Purpose                        |
| ---------------- | --------------------------------- | ----------- | ------------------------------ |
| **whisper**      | agent-cli-whisper (custom)        | 10300/10301 | Speech-to-text (Faster Whisper)|
| **tts**          | agent-cli-tts (custom)            | 10400/10401 | Text-to-speech (Kokoro/Piper)  |
| **ollama**       | ollama/ollama                     | 11434       | LLM server                     |
| **openwakeword** | rhasspy/wyoming-openwakeword      | 10500       | Wake word detection            |

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
```

### GPU Support

The CUDA profile automatically enables GPU for Whisper and TTS. For Ollama GPU support, edit the compose file and uncomment the `deploy` section under the ollama service.

## Managing Services

```bash
# Start services in background
docker compose -f docker/docker-compose.services.yml --profile cuda up -d

# Stop services
docker compose -f docker/docker-compose.services.yml --profile cuda down

# View logs
docker compose -f docker/docker-compose.services.yml logs -f

# Rebuild from source
docker compose -f docker/docker-compose.services.yml --profile cuda up --build
```

## Data Persistence

Services store data in Docker volumes:

- `agent-cli-whisper-cache` - Whisper models
- `agent-cli-tts-cache` - TTS models and voices
- `agent-cli-ollama-data` - Ollama models
- `agent-cli-openwakeword-data` - Wake word models

## Ports Reference

| Port  | Service      | Protocol |
| ----- | ------------ | -------- |
| 10300 | Whisper      | Wyoming  |
| 10301 | Whisper      | HTTP API |
| 10400 | TTS          | Wyoming  |
| 10401 | TTS          | HTTP API |
| 10500 | OpenWakeWord | Wyoming  |
| 11434 | Ollama       | HTTP API |

## Alternative: Native Installation

For better performance, consider platform-specific native installation:

- [macOS Native Setup](macos.md) - Metal GPU acceleration
- [Linux Native Setup](linux.md) - NVIDIA GPU acceleration
