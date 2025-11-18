# NVIDIA ASR Server

OpenAI-compatible API server for NVIDIA ASR models with support for multiple model backends.

## Features

- OpenAI-compatible `/v1/audio/transcriptions` endpoint
- Multiple model support via CLI
- Auto-GPU selection (selects GPU with most free memory)
- Word-level timestamp support (Parakeet model)
- Docker-free deployment using `uv`

## Supported Models

| Model | Description | Memory | Features |
|-------|-------------|--------|----------|
| `nvidia/canary-qwen-2.5b` | Multilingual ASR with translation | ~5GB | Multi-language, translation |
| `nvidia/parakeet-tdt-0.6b-v2` | High-quality English ASR | ~2GB | Timestamps, punctuation, 24min audio |

See [MODEL_SELECTION.md](MODEL_SELECTION.md) for detailed comparison and usage examples.

## Quick Start

```bash
cd scripts/canary-server

# Start with default model (Canary)
uv run server.py

# Start with Parakeet model
uv run server.py --model parakeet-tdt-0.6b-v2

# Custom configuration
uv run server.py -m parakeet-tdt-0.6b-v2 -p 9090 -d cuda:1
```

## CLI Options

```bash
uv run server.py --help
```

Options:
- `--model`, `-m`: Choose ASR model (`canary-qwen-2.5b` or `parakeet-tdt-0.6b-v2`)
- `--port`, `-p`: Server port (default: 9898)
- `--device`, `-d`: Device selection (auto-selects best GPU if not specified)

## API Usage

### Basic Transcription

```python
import requests

with open("audio.wav", "rb") as f:
    response = requests.post(
        "http://localhost:9898/v1/audio/transcriptions",
        files={"file": f},
        data={"model": "parakeet-tdt-0.6b-v2"}
    )

print(response.json()["text"])
```

### With Timestamps (Parakeet only)

```python
import requests

with open("audio.wav", "rb") as f:
    response = requests.post(
        "http://localhost:9898/v1/audio/transcriptions",
        files={"file": f},
        data={
            "model": "parakeet-tdt-0.6b-v2",
            "timestamp_granularities": ["word"]
        }
    )

result = response.json()
print(result["text"])

for word in result.get("words", []):
    print(f"{word['start']:.2f}s - {word['end']:.2f}s: {word['word']}")
```

### Using with Agent-CLI

```bash
# Start server
cd scripts/canary-server
uv run server.py -m parakeet-tdt-0.6b-v2

# In another terminal, use with agent-cli
agent-cli transcribe \
  --asr-provider openai \
  --asr-openai-base-url http://localhost:9898 \
  --asr-openai-model parakeet-tdt-0.6b-v2
```

## Requirements

- Python 3.13+
- CUDA-compatible GPU (recommended)
- ~2-5GB VRAM depending on model

## Development

The server is built with:
- **FastAPI**: Web framework
- **Typer**: CLI interface
- **NeMo**: NVIDIA's ASR toolkit
- **PyTorch**: Deep learning backend

Install dependencies:
```bash
cd scripts/canary-server
uv sync
```

## Architecture

```
server.py
├── CLI (Typer)
│   ├── Model selection
│   ├── Port configuration
│   └── Device selection
├── FastAPI App
│   └── /v1/audio/transcriptions
├── Model Loading
│   ├── SALM (Canary)
│   └── ASRModel (Parakeet)
└── Audio Processing
    └── FFmpeg resampling
```

## Troubleshooting

**Model not loading**:
- Check GPU memory: `nvidia-smi`
- Try smaller model: `--model parakeet-tdt-0.6b-v2`
- Use CPU: `--device cpu`

**Audio format issues**:
- Server auto-converts to 16kHz mono WAV
- Supports most common formats via FFmpeg

**Port already in use**:
```bash
uv run server.py --port 9999
```

## License

- Canary: NVIDIA AI Foundation Models Community License
- Parakeet: CC-BY-4.0

See individual model pages for details.
