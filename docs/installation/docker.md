# Docker Installation

Universal Docker setup that works on any platform with Docker support.

> **⚠️ Important Limitations**
>
> - **macOS**: Docker does not support GPU acceleration. For 10x better performance, use [macOS native setup](macos.md)
> - **Linux**: Limited GPU support. For full NVIDIA GPU acceleration, use [Linux native setup](linux.md)
> - **Ollama on macOS**: Can be memory-intensive without GPU acceleration

## Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available for Docker
- 10GB free disk space

## Quick Start

1. **Start the services:**

   ```bash
   docker compose -f docker/docker-compose.yml up --build
   ```

2. **Check if services are running:**

   ```bash
   docker compose -f docker/docker-compose.yml logs
   ```

   You should see logs from all services, with Ollama downloading the `gemma3:4b` model.

3. **Install agent-cli:**

   ```bash
   uv tools install agent-cli
   # or: pip install agent-cli
   ```

4. **Test the setup:**
   ```bash
   agent-cli autocorrect "this has an eror"
   ```

## Services Overview

The Docker setup provides:

| Service          | Image                        | Port  | Purpose                    |
| ---------------- | ---------------------------- | ----- | -------------------------- |
| **ollama**       | Custom build                 | 11434 | LLM server with gemma3:4b  |
| **whisper**      | rhasspy/wyoming-whisper      | 10300 | Speech-to-text (large-v3)  |
| **piper**        | rhasspy/wyoming-piper        | 10200 | Text-to-speech (ryan-high) |
| **openwakeword** | rhasspy/wyoming-openwakeword | 10400 | Wake word detection        |

## Configuration Files

The Docker setup uses:

- `docker/docker-compose.yml` - Service orchestration
- `docker/Dockerfile` - Custom Ollama container
- Data volumes for model persistence

## Important Limitations

- **macOS**: No GPU acceleration (10x slower than native)
- **Linux**: Limited GPU support
- **Memory**: Requires 8GB+ RAM for smooth operation

## Managing Services

```bash
# Start services in background
docker compose -f docker/docker-compose.yml up -d

# Stop services
docker compose -f docker/docker-compose.yml down

# View logs
docker compose -f docker/docker-compose.yml logs -f

# Restart a specific service
docker compose -f docker/docker-compose.yml restart ollama
```

## Data Persistence

Services store data in local directories:

- `./ollama/` - Ollama models and config
- `./whisper-data/` - Whisper models
- `./piper-data/` - Piper voice models
- `./openwakeword-data/` - Wake word models

## Troubleshooting

### Common Issues

- **Slow performance**: Use native setup for better performance
- **Memory issues**: Increase Docker memory allocation to 8GB+
- **Port conflicts**: Change port mappings in `docker/docker-compose.yml`

## Alternative: Native Installation

For better performance, consider platform-specific native installation:

- [macOS Native Setup](macos.md) - Metal GPU acceleration
- [Linux Native Setup](linux.md) - NVIDIA GPU acceleration
