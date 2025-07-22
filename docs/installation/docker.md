# Docker Installation

Universal Docker setup that works on any platform with Docker support.

> **⚠️ Important Limitations**
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
   docker compose -f docs/examples/docker-compose.yml up --build
   ```

2. **Check if services are running:**
   ```bash
   docker compose -f docs/examples/docker-compose.yml logs
   ```

   You should see logs from all services, with Ollama downloading the `qwen3:4b` model.

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

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **ollama** | Custom build | 11434 | LLM server with qwen3:4b |
| **whisper** | rhasspy/wyoming-whisper | 10300 | Speech-to-text (large-v3) |
| **piper** | rhasspy/wyoming-piper | 10200 | Text-to-speech (ryan-high) |
| **openwakeword** | rhasspy/wyoming-openwakeword | 10400 | Wake word detection |

## Configuration Files

The Docker setup uses:
- `docs/examples/docker-compose.yml` - Service orchestration
- `docs/examples/Dockerfile` - Custom Ollama container
- Data volumes for model persistence

## Memory Requirements

- **Minimum**: 8GB RAM
- **Recommended**: 12GB+ RAM for smooth operation
- **Ollama without GPU**: Uses significantly more RAM

## GPU Acceleration

### Linux with NVIDIA GPU

Uncomment the GPU section in `docker-compose.yml`:

```yaml
ollama:
  # ... other config ...
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
```

Requires:
- NVIDIA Docker runtime installed
- Compatible NVIDIA GPU

### macOS / Other Platforms

GPU acceleration is not available. Consider native installation for better performance.

## Managing Services

```bash
# Start services in background
docker compose -f docs/examples/docker-compose.yml up -d

# Stop services
docker compose -f docs/examples/docker-compose.yml down

# View logs
docker compose -f docs/examples/docker-compose.yml logs -f

# Restart a specific service
docker compose -f docs/examples/docker-compose.yml restart ollama
```

## Data Persistence

Services store data in local directories:
- `./ollama/` - Ollama models and config
- `./whisper-data/` - Whisper models
- `./piper-data/` - Piper voice models
- `./openwakeword-data/` - Wake word models

## Troubleshooting

### Ollama Memory Issues
- Increase Docker memory limit to 8GB+
- Consider switching to native installation on macOS

### Port Conflicts
- Change port mappings in `docker-compose.yml` if needed
- Update agent-cli config to match new ports

### Model Download Failures
- Check internet connection
- Ensure sufficient disk space
- Restart ollama service: `docker compose restart ollama`

### Performance Issues
- **macOS**: Use [native setup](macos.md) for 10x performance improvement
- **Linux**: Use [native setup](linux.md) for GPU acceleration
- Allocate more RAM to Docker

## Alternative: Native Installation

For better performance, consider platform-specific native installation:
- [macOS Native Setup](macos.md) - Metal GPU acceleration
- [Linux Native Setup](linux.md) - NVIDIA GPU acceleration
