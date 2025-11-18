# NVIDIA ASR Server

OpenAI-compatible API server for NVIDIA ASR models.

## Quick Start

```bash
cd scripts/nvidia-asr-server
uv run server.py
```

Server runs at `http://localhost:9898`

## CLI Options

- `--model`, `-m`: Model to use (default: `canary-qwen-2.5b`)
  - `canary-qwen-2.5b`: Multilingual ASR (~5GB VRAM)
  - `parakeet-tdt-0.6b-v2`: English with timestamps (~2GB VRAM)
- `--port`, `-p`: Port (default: 9898)
- `--device`, `-d`: Device (default: auto-select best GPU)

```bash
# Examples
uv run server.py --model parakeet-tdt-0.6b-v2
uv run server.py -m parakeet-tdt-0.6b-v2 -p 9090 -d cuda:1
```

## Using with Agent-CLI

```bash
# Start server
cd scripts/nvidia-asr-server
uv run server.py

# In another terminal
agent-cli transcribe \
  --asr-provider openai \
  --asr-openai-base-url http://localhost:9898/v1
```

**Note**: The `/v1` suffix is required for OpenAI compatibility.

## API Usage

### Python Example

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
response = requests.post(
    "http://localhost:9898/v1/audio/transcriptions",
    files={"file": open("audio.wav", "rb")},
    data={
        "model": "parakeet-tdt-0.6b-v2",
        "timestamp_granularities": ["word"]
    }
)

result = response.json()
for word in result.get("words", []):
    print(f"{word['start']:.2f}s - {word['end']:.2f}s: {word['word']}")
```

## Requirements

- Python 3.13+
- CUDA-compatible GPU (recommended)
- ~2-5GB VRAM depending on model

## Troubleshooting

**GPU out of memory**: Try smaller model or CPU
```bash
uv run server.py --model parakeet-tdt-0.6b-v2
uv run server.py --device cpu
```

**Port in use**: Change port
```bash
uv run server.py --port 9999
```

## License

- Canary: NVIDIA AI Foundation Models Community License
- Parakeet: CC-BY-4.0
