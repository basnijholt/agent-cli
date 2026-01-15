# Whisper Server with TTL-Based Model Unloading

## Overview

Add a self-hosted Whisper ASR server to agent-cli that:
- Runs `faster-whisper` model directly (GPU-accelerated)
- Exposes **OpenAI-compatible API** (`/v1/audio/transcriptions`)
- Exposes **Wyoming protocol** (Home Assistant integration)
- **TTL-based model unloading** - unloads from VRAM when idle
- Supports **multiple models** with independent TTLs
- Includes **Prometheus metrics** for monitoring
- Supports **WebSocket streaming** for real-time transcription

## Architecture

### CLI Structure

```bash
# Subcommand approach
agent-cli server whisper --model large-v3 --ttl 300 --port 5000
agent-cli server proxy   # existing behavior (renamed from default)
```

### Model Management

```
┌──────────────────────────────────────────────────────────────────┐
│                     WhisperModelRegistry                          │
├──────────────────────────────────────────────────────────────────┤
│  models: dict[str, WhisperModelManager]                          │
│  default_model: str                                              │
├──────────────────────────────────────────────────────────────────┤
│  + get_manager(model_name) → WhisperModelManager                 │
│  + register_model(name, config) → None                           │
│  + list_models() → list[ModelStatus]                             │
│  + unload_all() → None                                           │
└──────────────────────────────────────────────────────────────────┘
           │
           │ manages multiple
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     WhisperModelManager                           │
├──────────────────────────────────────────────────────────────────┤
│  model_name: str                                                 │
│  model: WhisperModel | None                                      │
│  config: ModelConfig (device, compute_type, ttl)                 │
│  stats: ModelStats (requests, load_time, last_used)              │
├──────────────────────────────────────────────────────────────────┤
│  + get_model() → WhisperModel    # Lazy load + reset TTL         │
│  + transcribe(...) → str         # Thread-safe transcription     │
│  + start_unload_watcher()        # Background TTL checker        │
│  + unload_model()                # Manual/TTL unload             │
└──────────────────────────────────────────────────────────────────┘
```

### Model Lifecycle

```
[Startup]                    [First Request]              [Idle > TTL]
   │                              │                            │
   ▼                              ▼                            ▼
No model loaded ──────────► Load model ──────────────────► Unload model
   │                              │                            │
   │                              ▼                            │
   │                        Reset TTL timer                    │
   │                              │                            │
   └──────────────────────────────┴────────────────────────────┘
                                  │
                            [Next Request]
```

## File Structure

```
agent_cli/
├── server/
│   ├── __init__.py
│   ├── cli.py                    # Typer app with whisper/proxy subcommands
│   │
│   ├── whisper/
│   │   ├── __init__.py
│   │   ├── api.py                # FastAPI app with all routes
│   │   ├── model_manager.py      # Single model lifecycle + TTL
│   │   ├── model_registry.py     # Multi-model management
│   │   ├── wyoming_handler.py    # Wyoming protocol
│   │   ├── streaming.py          # WebSocket streaming logic
│   │   └── metrics.py            # Prometheus metrics definitions
│   │
│   └── proxy/
│       ├── __init__.py
│       └── api.py                # Existing api.py (moved)
```

## API Endpoints

### OpenAI-Compatible

```
POST /v1/audio/transcriptions
POST /v1/audio/translations
```

### WebSocket Streaming

```
WS /v1/audio/transcriptions/stream
```

Protocol:
- Client → Server: Binary audio chunks (16kHz, 16-bit, mono PCM)
- Server → Client: JSON messages with partial/final transcripts

### Health & Metrics

```
GET /health          # Server and model status
GET /metrics         # Prometheus metrics
POST /v1/model/unload?model=large-v3  # Manual unload
```

## CLI Options

```bash
agent-cli server whisper [OPTIONS]

# Model Configuration
  --model TEXT              Model name(s) to load [default: large-v3]
  --default-model TEXT      Default model for requests
  --device TEXT             Device: auto, cuda, cpu [default: auto]
  --compute-type TEXT       Compute type [default: auto]
  --cache-dir PATH          Model cache directory

# TTL Configuration
  --ttl INTEGER             Seconds before unloading [default: 300]
  --preload                 Load at startup (not lazy)

# Server Configuration
  --host TEXT               Bind address [default: 0.0.0.0]
  --port INTEGER            HTTP port [default: 5000]
  --wyoming-port INTEGER    Wyoming port [default: 3001]
  --no-wyoming              Disable Wyoming server
  --no-metrics              Disable Prometheus

# Utility
  --download-only           Download model(s) and exit
```

## Prometheus Metrics

- `whisper_transcription_requests_total` - Counter by model/status
- `whisper_transcription_duration_seconds` - Histogram
- `whisper_audio_duration_seconds` - Histogram
- `whisper_model_loaded` - Gauge by model
- `whisper_model_load_time_seconds` - Gauge
- `whisper_model_ttl_remaining_seconds` - Gauge
- `whisper_active_requests` - Gauge

## Configuration

```toml
[server.whisper]
default_model = "large-v3"
host = "0.0.0.0"
port = 5000
wyoming_port = 3001

[server.whisper.models.large-v3]
device = "cuda"
compute_type = "float16"
ttl = 600

[server.whisper.models.small]
device = "cuda"
compute_type = "int8"
ttl = 60
```

## Dependencies

New optional dependency group:
```toml
[project.optional-dependencies]
whisper = ["faster-whisper", "prometheus-client"]
```

## Implementation Phases

1. **Core Model Management** - WhisperModelManager with TTL
2. **HTTP API** - OpenAI-compatible endpoints + Prometheus
3. **Streaming & Wyoming** - WebSocket + Wyoming protocol
4. **CLI Integration** - Server subcommands + config
