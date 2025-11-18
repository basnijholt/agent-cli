#!/usr/bin/env -S uv run
"""NVIDIA ASR server with OpenAI-compatible API.

Supports multiple NVIDIA ASR models:
- nvidia/canary-qwen-2.5b (default): Multilingual ASR with translation capabilities
- nvidia/parakeet-tdt-0.6b-v2: High-quality English ASR with timestamps

Usage:
    cd scripts/nvidia-asr-server
    uv run server.py
    uv run server.py --model parakeet-tdt-0.6b-v2
    uv run server.py --port 9090 --device cuda:1
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import traceback
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import torch
import typer
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import TypedDict

    class TranscriptionResult(TypedDict, total=False):
        """Transcription result with optional word-level timestamps."""

        text: str
        words: list[dict[str, Any]]


class ModelType(str, Enum):
    """Supported ASR models."""

    CANARY = "canary-qwen-2.5b"
    PARAKEET = "parakeet-tdt-0.6b-v2"


@dataclass
class ServerConfig:
    """Server configuration."""

    model_type: ModelType
    device: str
    port: int


def select_best_gpu() -> str:
    """Select the GPU with the most free memory, or CPU if no GPU available."""
    if not torch.cuda.is_available():
        return "cpu"

    if torch.cuda.device_count() == 1:
        return "cuda:0"

    best_gpu = max(
        range(torch.cuda.device_count()),
        key=lambda i: torch.cuda.mem_get_info(i)[0],
    )
    return f"cuda:{best_gpu}"


def resample_audio(input_path: str) -> str:
    """Resample audio to 16kHz mono WAV using ffmpeg."""
    out_path = f"{input_path}_16k.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode() if result.stderr else "No error output"
        msg = f"ffmpeg failed: {stderr}"
        raise RuntimeError(msg)
    return out_path


def load_asr_model(config: ServerConfig) -> Any:
    """Load the appropriate ASR model based on configuration."""
    import nemo.collections.asr as nemo_asr  # noqa: PLC0415
    from nemo.collections.speechlm2.models import SALM  # noqa: PLC0415

    model_name = f"nvidia/{config.model_type.value}"

    # Print device info
    if config.device.startswith("cuda"):
        gpu_id = int(config.device.split(":")[1]) if ":" in config.device else 0
        free_mem, total_mem = torch.cuda.mem_get_info(gpu_id)
        free_gb = free_mem / 1024**3
        total_gb = total_mem / 1024**3
        print(
            f"Loading {model_name} on {config.device} ({free_gb:.1f}GB / {total_gb:.1f}GB)",
            flush=True,
        )
    else:
        print(f"Loading {model_name} on {config.device}", flush=True)

    if config.model_type == ModelType.CANARY:
        model = SALM.from_pretrained(model_name)
    elif config.model_type == ModelType.PARAKEET:
        model = nemo_asr.models.ASRModel.from_pretrained(model_name)
    else:
        msg = f"Unsupported model type: {config.model_type}"
        raise ValueError(msg)

    return model.to(config.device).eval()


asr_model: Any = None
config: ServerConfig | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """Load the ASR model on startup."""
    global asr_model
    assert config is not None
    asr_model = load_asr_model(config)
    yield


app = FastAPI(lifespan=lifespan)


def transcribe_canary(audio_path: str, prompt: str | None) -> str:
    """Transcribe audio using Canary model."""
    user_prompt = prompt or "Transcribe the following:"
    full_prompt = f"{user_prompt} {asr_model.audio_locator_tag}"

    prompts = [[{"role": "user", "content": full_prompt, "audio": [audio_path]}]]
    answer_ids = asr_model.generate(prompts=prompts, max_new_tokens=128)
    return asr_model.tokenizer.ids_to_text(answer_ids[0].cpu())


def transcribe_parakeet(
    audio_path: str,
    timestamp_granularities: list[str] | None,
) -> TranscriptionResult:
    """Transcribe audio using Parakeet model."""
    enable_timestamps = bool(timestamp_granularities)
    output = asr_model.transcribe([audio_path], timestamps=enable_timestamps)

    result: TranscriptionResult = {"text": output[0].text}

    if enable_timestamps and timestamp_granularities and "word" in timestamp_granularities:
        word_timestamps = output[0].timestamp.get("word", [])
        if word_timestamps:
            result["words"] = [
                {"word": w["word"], "start": w["start"], "end": w["end"]} for w in word_timestamps
            ]

    return result


def cleanup_files(*paths: str | None) -> None:
    """Clean up temporary files."""
    for p in paths:
        if p:
            with suppress(OSError):
                Path(p).unlink(missing_ok=True)


@app.post("/v1/audio/transcriptions", response_model=None)
async def transcribe(
    file: Annotated[UploadFile, File()],
    response_format: Annotated[str, Form()] = "json",
    prompt: Annotated[str | None, Form()] = None,
    timestamp_granularities: Annotated[list[str] | None, Form()] = None,
) -> str | JSONResponse:
    """Transcribe audio using ASR model with OpenAI-compatible API."""
    if asr_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    with tempfile.NamedTemporaryFile(delete=False, suffix="") as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    resampled_path = None
    try:
        resampled_path = resample_audio(tmp_path)

        with torch.inference_mode():
            assert config is not None
            if config.model_type == ModelType.CANARY:
                text = transcribe_canary(resampled_path, prompt)
                return text if response_format == "text" else JSONResponse({"text": text})
            if config.model_type == ModelType.PARAKEET:
                result = transcribe_parakeet(resampled_path, timestamp_granularities)
                return result["text"] if response_format == "text" else JSONResponse(result)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        cleanup_files(tmp_path, resampled_path)


def main(
    model: Annotated[
        ModelType,
        typer.Option("--model", "-m", help="ASR model to use"),
    ] = ModelType.CANARY,
    port: Annotated[int, typer.Option("--port", "-p", help="Server port")] = 9898,
    device: Annotated[
        str | None,
        typer.Option(
            "--device",
            "-d",
            help="Device to use (cpu, cuda, cuda:0, etc.). Auto-selects GPU with most free memory if not specified.",
        ),
    ] = None,
) -> None:
    """Run NVIDIA ASR server with OpenAI-compatible API.

    Supports multiple models:
    - canary-qwen-2.5b: Multilingual ASR with translation (default)
    - parakeet-tdt-0.6b-v2: High-quality English ASR with timestamps
    """
    global config

    config = ServerConfig(
        model_type=model,
        device=device or select_best_gpu(),
        port=port,
    )

    print(f"Starting ASR server with model: {model.value}")
    print(f"Device: {config.device}")
    print(f"Port: {config.port}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=config.port)  # noqa: S104


if __name__ == "__main__":
    typer.run(main)
