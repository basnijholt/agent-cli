#!/usr/bin/env -S uv run
"""NVIDIA Canary ASR server with OpenAI-compatible API.

Usage:
    cd scripts/canary-server
    uv run server.py

Environment variables:
    CANARY_PORT: Server port (default: 9898)
    CANARY_DEVICE: Device to use (default: auto-select GPU with most free memory)
                   Options: cpu, cuda, cuda:0, cuda:1, etc.
"""

import os
import shutil
import subprocess
import tempfile
import traceback
from contextlib import suppress
from pathlib import Path
from typing import Annotated

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from nemo.collections.speechlm2.models import SALM


def select_best_gpu() -> str:
    """Select the GPU with the most free memory, or CPU if no GPU available."""
    if not torch.cuda.is_available():
        return "cpu"

    # If only one GPU, use it
    if torch.cuda.device_count() == 1:
        return "cuda:0"

    # Find GPU with most free memory
    max_free_memory = 0
    best_gpu = 0

    for i in range(torch.cuda.device_count()):
        free_memory = torch.cuda.mem_get_info(i)[0]  # Returns (free, total)
        if free_memory > max_free_memory:
            max_free_memory = free_memory
            best_gpu = i

    return f"cuda:{best_gpu}"


app = FastAPI()
salm_model = None
DEVICE = os.getenv("CANARY_DEVICE") or select_best_gpu()
PORT = int(os.getenv("CANARY_PORT", "9898"))


def ffmpeg_resample_to_16k_mono(input_path: str) -> str:
    """Resample audio to 16kHz mono WAV using ffmpeg."""
    out_path = input_path + "_16k.wav"
    # Try with format auto-detection first, then try as raw PCM if that fails
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "s16le",  # Assume signed 16-bit little-endian PCM
        "-ar",
        "16000",  # Input sample rate (agent-cli uses 16kHz)
        "-ac",
        "1",  # Input is mono
        "-i",
        input_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        out_path,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode() if e.stderr else "No error output"
        msg = f"ffmpeg failed: {stderr_msg}"
        raise RuntimeError(msg) from e
    return out_path


def ensure_16k_mono(path: str) -> str:
    """Convert any audio format to 16kHz mono WAV using ffmpeg."""
    # Always use ffmpeg for format conversion and resampling
    # This handles any input format including raw PCM data
    return ffmpeg_resample_to_16k_mono(path)


@app.on_event("startup")
async def load_model() -> None:
    """Load the Canary model on startup."""
    global salm_model

    # Print device info
    if DEVICE.startswith("cuda"):
        gpu_id = int(DEVICE.split(":")[1]) if ":" in DEVICE else 0
        free_mem, total_mem = torch.cuda.mem_get_info(gpu_id)
        free_gb = free_mem / 1024**3
        total_gb = total_mem / 1024**3
        print(
            f"Loading nvidia/canary-qwen-2.5b on {DEVICE} "
            f"({free_gb:.1f}GB free / {total_gb:.1f}GB total)",
            flush=True,
        )
    else:
        print(f"Loading nvidia/canary-qwen-2.5b on {DEVICE}", flush=True)

    salm_model = SALM.from_pretrained("nvidia/canary-qwen-2.5b").to(DEVICE).eval()


@app.post("/v1/audio/transcriptions", response_model=None)
async def transcribe(
    file: Annotated[UploadFile, File()] = ...,
    model_name: Annotated[str | None, Form(alias="model")] = None,  # noqa: ARG001
    language: Annotated[str | None, Form()] = None,  # noqa: ARG001
    response_format: Annotated[str, Form()] = "json",
    prompt: Annotated[str | None, Form()] = None,
) -> str | JSONResponse:
    """Transcribe audio using Canary model with OpenAI-compatible API."""
    if salm_model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    # Save uploaded file to a temp file (no extension, let ffmpeg auto-detect)
    with tempfile.NamedTemporaryFile(delete=False, suffix="") as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    out_path = None
    try:
        # Ensure 16k mono WAV for SALM
        out_path = ensure_16k_mono(tmp_path)

        user_prompt = prompt or "Transcribe the following:"
        full_prompt = f"{user_prompt} {salm_model.audio_locator_tag}"

        prompts = [
            [
                {
                    "role": "user",
                    "content": full_prompt,
                    "audio": [out_path],
                },
            ],
        ]

        with torch.inference_mode():
            answer_ids = salm_model.generate(
                prompts=prompts,
                max_new_tokens=128,
            )

        text = salm_model.tokenizer.ids_to_text(answer_ids[0].cpu())

        if response_format == "text":
            return text
        return JSONResponse({"text": text})

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        for p in (tmp_path, out_path):
            if p:
                path = Path(p)
                if path.exists():
                    with suppress(OSError):
                        path.unlink()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # noqa: S104
