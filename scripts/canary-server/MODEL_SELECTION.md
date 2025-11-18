# ASR Model Selection Guide

The server now supports multiple NVIDIA ASR models with easy CLI-based selection.

## Supported Models

### 1. Canary-Qwen-2.5b (Default)
- **Model ID**: `nvidia/canary-qwen-2.5b`
- **Type**: Multilingual ASR with translation capabilities
- **Memory**: ~5GB VRAM
- **Use Cases**: Multilingual transcription, translation tasks
- **CLI Flag**: `--model canary-qwen-2.5b` or `-m canary-qwen-2.5b`

### 2. Parakeet-TDT-0.6b-v2
- **Model ID**: `nvidia/parakeet-tdt-0.6b-v2`
- **Type**: High-quality English ASR with timestamps
- **Memory**: ~2GB VRAM
- **Parameters**: 600 million
- **Features**:
  - Word-level timestamp predictions
  - Automatic punctuation and capitalization
  - Support for spoken numbers and song lyrics
  - Can handle audio up to 24 minutes in a single pass
  - RTFx of 3380 on HF-Open-ASR leaderboard (batch size 128)
- **Use Cases**: English-only transcription, subtitle generation, voice analytics
- **CLI Flag**: `--model parakeet-tdt-0.6b-v2` or `-m parakeet-tdt-0.6b-v2`

## Usage Examples

### Start with default model (Canary)
```bash
cd scripts/canary-server
uv run server.py
```

### Start with Parakeet model
```bash
uv run server.py --model parakeet-tdt-0.6b-v2
# or short form:
uv run server.py -m parakeet-tdt-0.6b-v2
```

### Custom port and device
```bash
uv run server.py --model parakeet-tdt-0.6b-v2 --port 9090 --device cuda:1
# or short form:
uv run server.py -m parakeet-tdt-0.6b-v2 -p 9090 -d cuda:1
```

## CLI Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--model` | `-m` | `canary-qwen-2.5b` | ASR model to use |
| `--port` | `-p` | `9898` | Server port |
| `--device` | `-d` | Auto-select | Device (cpu, cuda, cuda:0, etc.) |

## API Usage with Timestamps (Parakeet only)

The Parakeet model supports word-level timestamps through the OpenAI-compatible API:

```python
import requests

with open("audio.wav", "rb") as f:
    response = requests.post(
        "http://localhost:9898/v1/audio/transcriptions",
        files={"file": f},
        data={
            "model": "parakeet-tdt-0.6b-v2",
            "response_format": "json",
            "timestamp_granularities": ["word"]
        }
    )

result = response.json()
print(result["text"])

# Access word-level timestamps
for word in result.get("words", []):
    print(f"{word['start']:.2f}s - {word['end']:.2f}s: {word['word']}")
```

## Help

```bash
uv run server.py --help
```

## Model Comparison

| Feature | Canary-Qwen-2.5b | Parakeet-TDT-0.6b-v2 |
|---------|------------------|----------------------|
| Languages | Multilingual | English only |
| Translation | Yes | No |
| Timestamps | No | Yes (word-level) |
| Memory | ~5GB | ~2GB |
| Parameters | 2.5B | 600M |
| Max Audio Length | Variable | 24 minutes |
| Punctuation | Yes | Yes |
| Capitalization | Yes | Yes |

## License

Both models are available for commercial and non-commercial use:
- Canary: NVIDIA AI Foundation Models Community License
- Parakeet: CC-BY-4.0
