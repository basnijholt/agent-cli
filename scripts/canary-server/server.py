#!/usr/bin/env -S uv run
# ruff: noqa: D103, ANN201, FAST002, B008, ARG001, B904, TRY003, EM102, PTH110, SIM105, PTH108, S104, F841, PLC0415
"""NVIDIA Canary ASR server with OpenAI-compatible API.

Usage:
    cd scripts/canary-server
    uv run server.py

Environment variables:
    CANARY_PORT: Server port (default: 9898)
    CANARY_DEVICE: Device to use (default: cuda if available, else cpu)
"""

import os
import shutil
import subprocess
import tempfile

import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from nemo.collections.speechlm2.models import SALM

app = FastAPI()
salm_model = None
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PORT = int(os.getenv("CANARY_PORT", "9898"))


def ffmpeg_resample_to_16k_mono(input_path: str) -> str:
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
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else "No error output"
        raise RuntimeError(f"ffmpeg failed: {stderr}")
    return out_path


def ensure_16k_mono(path: str) -> str:
    """Convert any audio format to 16kHz mono WAV using ffmpeg."""
    # Always use ffmpeg for format conversion and resampling
    # This handles any input format including raw PCM data
    return ffmpeg_resample_to_16k_mono(path)


@app.on_event("startup")
async def load_model():
    global salm_model
    print("Loading nvidia/canary-qwen-2.5b on", DEVICE, flush=True)
    salm_model = SALM.from_pretrained("nvidia/canary-qwen-2.5b").to(DEVICE).eval()


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_name: str = Form(None, alias="model"),
    language: str = Form(None),
    response_format: str = Form("json"),
    prompt: str = Form(None),
):
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
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in (tmp_path, out_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
