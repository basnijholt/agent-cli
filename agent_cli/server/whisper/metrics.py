"""Prometheus metrics for Whisper server."""

from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Check if prometheus_client is available
HAS_PROMETHEUS = find_spec("prometheus_client") is not None

# Metrics will be initialized lazily
_metrics_initialized = False

# Metric instances (None if prometheus not available)
TRANSCRIPTION_REQUESTS: Counter | None = None
TRANSCRIPTION_DURATION: Histogram | None = None
AUDIO_DURATION: Histogram | None = None
MODEL_LOADED: Gauge | None = None
MODEL_LOAD_TIME: Gauge | None = None
MODEL_TTL_REMAINING: Gauge | None = None
ACTIVE_REQUESTS: Gauge | None = None


def init_metrics() -> bool:
    """Initialize Prometheus metrics.

    Returns:
        True if metrics were initialized, False if prometheus_client is not available.

    """
    global _metrics_initialized
    global TRANSCRIPTION_REQUESTS, TRANSCRIPTION_DURATION, AUDIO_DURATION
    global MODEL_LOADED, MODEL_LOAD_TIME, MODEL_TTL_REMAINING, ACTIVE_REQUESTS

    if _metrics_initialized:
        return HAS_PROMETHEUS

    if not HAS_PROMETHEUS:
        logger.info("prometheus_client not installed, metrics disabled")
        return False

    from prometheus_client import Counter, Gauge, Histogram  # noqa: PLC0415

    TRANSCRIPTION_REQUESTS = Counter(
        "whisper_transcription_requests_total",
        "Total transcription requests",
        ["model", "status"],
    )

    TRANSCRIPTION_DURATION = Histogram(
        "whisper_transcription_duration_seconds",
        "Time spent transcribing audio",
        ["model"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    )

    AUDIO_DURATION = Histogram(
        "whisper_audio_duration_seconds",
        "Duration of audio files transcribed",
        ["model"],
        buckets=[1, 5, 10, 30, 60, 120, 300, 600],
    )

    MODEL_LOADED = Gauge(
        "whisper_model_loaded",
        "Whether model is currently loaded (1=loaded, 0=unloaded)",
        ["model"],
    )

    MODEL_LOAD_TIME = Gauge(
        "whisper_model_load_time_seconds",
        "Time taken to load model",
        ["model"],
    )

    MODEL_TTL_REMAINING = Gauge(
        "whisper_model_ttl_remaining_seconds",
        "Seconds until model unloads due to TTL",
        ["model"],
    )

    ACTIVE_REQUESTS = Gauge(
        "whisper_active_requests",
        "Number of currently processing requests",
        ["model"],
    )

    _metrics_initialized = True
    logger.info("Prometheus metrics initialized")
    return True


def record_transcription_start(model: str) -> None:
    """Record the start of a transcription request."""
    if ACTIVE_REQUESTS is not None:
        ACTIVE_REQUESTS.labels(model=model).inc()


def record_transcription_complete(
    model: str,
    duration: float,
    audio_duration: float,
    *,
    success: bool,
) -> None:
    """Record completion of a transcription request."""
    status = "success" if success else "error"

    if TRANSCRIPTION_REQUESTS is not None:
        TRANSCRIPTION_REQUESTS.labels(model=model, status=status).inc()

    if success:
        if TRANSCRIPTION_DURATION is not None:
            TRANSCRIPTION_DURATION.labels(model=model).observe(duration)

        if AUDIO_DURATION is not None:
            AUDIO_DURATION.labels(model=model).observe(audio_duration)

    if ACTIVE_REQUESTS is not None:
        ACTIVE_REQUESTS.labels(model=model).dec()


def update_model_status(
    model: str,
    *,
    loaded: bool,
    load_time: float | None = None,
    ttl_remaining: float | None = None,
    active_requests: int = 0,
) -> None:
    """Update model status metrics."""
    if MODEL_LOADED is not None:
        MODEL_LOADED.labels(model=model).set(1 if loaded else 0)

    if MODEL_LOAD_TIME is not None and load_time is not None:
        MODEL_LOAD_TIME.labels(model=model).set(load_time)

    if MODEL_TTL_REMAINING is not None:
        MODEL_TTL_REMAINING.labels(model=model).set(ttl_remaining if ttl_remaining else 0)

    if ACTIVE_REQUESTS is not None:
        ACTIVE_REQUESTS.labels(model=model).set(active_requests)
