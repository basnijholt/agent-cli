#!/usr/bin/env python3
"""Reproduce (and validate the fix for) the MLX Whisper Metal buffer-cache leak.

Background
----------
The MLX Whisper backend runs ``mlx_whisper.transcribe`` in a long-lived
subprocess. With ``--ttl 0`` the subprocess is never recycled, so MLX's Metal
buffer cache is never released between requests. It grows to the largest working
set ever seen (driven by the longest audio clip) and eventually gets pushed to
swap, degrading latency (swapped-out Metal buffers must fault back in).

This harness loads large-v3 via ``mlx_whisper`` and transcribes many requests
while cycling clip lengths, logging MLX memory counters per request to a CSV.

Modes
-----
* baseline (default): never release the cache -> ``get_cache_memory`` climbs and
  stays at the high-water mark of the largest working set.
* ``--clear-cache``: call ``mx.clear_cache()`` after every request -> cache stays
  flat/bounded. Model weights (live arrays) are untouched, so inference stays hot.
* ``--set-cache-limit BYTES``: call ``mx.set_cache_limit(BYTES)`` once at load as
  an alternative bound (no per-request call).

Usage
-----
    uv run python tools/repro_cache_leak.py --requests 100 --out baseline.csv
    uv run python tools/repro_cache_leak.py --requests 100 --clear-cache --out fixed.csv

This loads a SECOND copy of large-v3 in this process (~3 GB weights + working
set). Watch ``memory_pressure`` and abort if the machine starts swapping.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import mlx.core as mx
import mlx_whisper
import numpy as np

# Reuse the backend's canonical-name -> HF-repo resolver so we hit the SAME
# already-downloaded HF cache the service uses (no re-download).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_cli.server.whisper.backends.mlx import _resolve_mlx_model_name

SAMPLE_RATE = 16000
# Clip lengths (seconds) cycled across requests. The longer clips (>30s) span
# multiple 30s Whisper windows and drive the largest working set / cache growth.
CLIP_LENGTHS = (0.5, 2.0, 5.0, 10.0, 20.0, 30.0)


def _synth_clip(seconds: float, seed: int) -> np.ndarray:
    """Synthesize a deterministic mono 16kHz float32 clip.

    A low-amplitude tone plus a little noise so Whisper actually runs its
    encoder/decoder (pure silence can short-circuit) without needing real audio.
    """
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * seconds)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    freq = 180.0 + (seed % 5) * 40.0
    tone = 0.05 * np.sin(2.0 * np.pi * freq * t, dtype=np.float32)
    noise = (0.005 * rng.standard_normal(n)).astype(np.float32)
    return (tone + noise).astype(np.float32)


def _mb(nbytes: int) -> float:
    return nbytes / (1024.0 * 1024.0)


def _run_requests(
    repo: str,
    requests: int,
    *,
    clear_cache: bool,
) -> tuple[list[dict[str, float | int | str]], float, float]:
    """Transcribe ``requests`` clips, logging MLX memory counters per request.

    Returns (rows, total_infer_seconds, total_clear_seconds).
    """
    rows: list[dict[str, float | int | str]] = []
    total_clear_s = 0.0
    total_infer_s = 0.0
    for i in range(requests):
        seconds = CLIP_LENGTHS[i % len(CLIP_LENGTHS)]
        clip = _synth_clip(seconds, seed=i + 1)

        infer_start = time.perf_counter()
        mlx_whisper.transcribe(clip, path_or_hf_repo=repo, temperature=0.0)
        infer_s = time.perf_counter() - infer_start
        total_infer_s += infer_s

        clear_s = 0.0
        if clear_cache:
            clear_start = time.perf_counter()
            mx.clear_cache()
            clear_s = time.perf_counter() - clear_start
            total_clear_s += clear_s

        active = mx.get_active_memory()
        cache = mx.get_cache_memory()
        peak = mx.get_peak_memory()
        rows.append(
            {
                "request": i,
                "clip_seconds": seconds,
                "infer_s": round(infer_s, 4),
                "clear_s": round(clear_s, 6),
                "active_mb": round(_mb(active), 2),
                "cache_mb": round(_mb(cache), 2),
                "peak_mb": round(_mb(peak), 2),
            },
        )
        if i % 10 == 0 or i == requests - 1:
            print(
                f"[{i:3d}] clip={seconds:4.1f}s infer={infer_s:5.2f}s "
                f"active={_mb(active):7.1f}MB cache={_mb(cache):7.1f}MB peak={_mb(peak):7.1f}MB",
            )
    return rows, total_infer_s, total_clear_s


def main() -> None:
    """Parse args, run the request loop, write the CSV, and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="large-v3", help="Model name (canonical or HF repo).")
    parser.add_argument("--requests", type=int, default=100, help="Number of transcribe requests.")
    parser.add_argument("--out", type=Path, required=True, help="CSV output path.")
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Call mx.clear_cache() after each request (the proposed fix).",
    )
    parser.add_argument(
        "--set-cache-limit",
        type=int,
        default=None,
        metavar="BYTES",
        help="Call mx.set_cache_limit(BYTES) once at load as an alternative bound.",
    )
    args = parser.parse_args()

    repo = _resolve_mlx_model_name(args.model)
    print(f"[repro] mlx {mx.__version__} | model {args.model} -> {repo}")
    print(
        f"[repro] mode: {'clear_cache' if args.clear_cache else 'baseline'}"
        + (f" | set_cache_limit={args.set_cache_limit}" if args.set_cache_limit is not None else ""),
    )

    # Warm-load the model (first transcribe pulls weights into the cache).
    if args.set_cache_limit is not None:
        mx.set_cache_limit(args.set_cache_limit)
    load_start = time.perf_counter()
    _ = mlx_whisper.transcribe(_synth_clip(1.0, 0), path_or_hf_repo=repo, temperature=0.0)
    load_s = time.perf_counter() - load_start
    print(f"[repro] warm load + first transcribe: {load_s:.2f}s")

    rows, total_infer_s, total_clear_s = _run_requests(
        repo,
        args.requests,
        clear_cache=args.clear_cache,
    )

    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    cache_series = [r["cache_mb"] for r in rows]
    print("\n===== SUMMARY =====")
    print(f"model              : {args.model} -> {repo}")
    print(f"requests           : {args.requests}")
    print(f"mode               : {'clear_cache' if args.clear_cache else 'baseline'}")
    print(f"cache_mb  peak     : {max(cache_series):.1f} MB")
    print(f"cache_mb  final    : {cache_series[-1]:.1f} MB")
    print(f"active_mb final    : {rows[-1]['active_mb']:.1f} MB")
    print(f"peak_mb   final    : {rows[-1]['peak_mb']:.1f} MB")
    print(f"infer/req  mean    : {total_infer_s / args.requests * 1000:.1f} ms")
    if args.clear_cache:
        print(f"clear/req  mean    : {total_clear_s / args.requests * 1000:.3f} ms")
        print(f"clear      total   : {total_clear_s * 1000:.1f} ms over {args.requests} reqs")
    print(f"csv                : {args.out}")


if __name__ == "__main__":
    main()
