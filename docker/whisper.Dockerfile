# Multi-target Dockerfile for agent-cli Whisper ASR server
# Supports both CUDA (GPU) and CPU-only builds
#
# Build examples:
#   docker build -f docker/whisper.Dockerfile --target cuda -t agent-cli-whisper:cuda .
#   docker build -f docker/whisper.Dockerfile --target cpu -t agent-cli-whisper:cpu .
#
# Run examples:
#   docker run -p 10300:10300 -p 10301:10301 --gpus all agent-cli-whisper:cuda
#   docker run -p 10300:10300 -p 10301:10301 agent-cli-whisper:cpu

# =============================================================================
# Base stage: common dependencies
# =============================================================================
FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 whisper

WORKDIR /app

# Expose ports: Wyoming (10300) and HTTP API (10301)
EXPOSE 10300 10301

# Default environment variables
ENV WHISPER_HOST=0.0.0.0 \
    WHISPER_PORT=10301 \
    WHISPER_WYOMING_PORT=10300 \
    WHISPER_MODEL=large-v3 \
    WHISPER_TTL=300 \
    WHISPER_LOG_LEVEL=info

# =============================================================================
# CUDA target: GPU-accelerated with faster-whisper
# =============================================================================
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS cuda

# Install system dependencies (same as base but on Ubuntu)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3-pip \
        ffmpeg \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

# Create non-root user
RUN useradd -m -u 1000 whisper

WORKDIR /app

# Install agent-cli with whisper support
RUN pip install --no-cache-dir "agent-cli[whisper]"

# Create cache directory for models
RUN mkdir -p /home/whisper/.cache && chown -R whisper:whisper /home/whisper

USER whisper

# Expose ports: Wyoming (10300) and HTTP API (10301)
EXPOSE 10300 10301

# Default environment variables
ENV WHISPER_HOST=0.0.0.0 \
    WHISPER_PORT=10301 \
    WHISPER_WYOMING_PORT=10300 \
    WHISPER_MODEL=large-v3 \
    WHISPER_TTL=300 \
    WHISPER_LOG_LEVEL=info \
    WHISPER_DEVICE=cuda

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${WHISPER_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server whisper \
    --host ${WHISPER_HOST} \
    --port ${WHISPER_PORT} \
    --wyoming-port ${WHISPER_WYOMING_PORT} \
    --model ${WHISPER_MODEL} \
    --ttl ${WHISPER_TTL} \
    --device ${WHISPER_DEVICE} \
    --log-level ${WHISPER_LOG_LEVEL} \
    ${WHISPER_EXTRA_ARGS:-}"]

# =============================================================================
# CPU target: CPU-only with faster-whisper
# =============================================================================
FROM base AS cpu

# Install agent-cli with whisper support
RUN pip install --no-cache-dir "agent-cli[whisper]"

# Create cache directory for models
RUN mkdir -p /home/whisper/.cache && chown -R whisper:whisper /home/whisper

USER whisper

# Override device for CPU
ENV WHISPER_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${WHISPER_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server whisper \
    --host ${WHISPER_HOST} \
    --port ${WHISPER_PORT} \
    --wyoming-port ${WHISPER_WYOMING_PORT} \
    --model ${WHISPER_MODEL} \
    --ttl ${WHISPER_TTL} \
    --device ${WHISPER_DEVICE} \
    --log-level ${WHISPER_LOG_LEVEL} \
    ${WHISPER_EXTRA_ARGS:-}"]
