# Multi-target Dockerfile for agent-cli TTS server
# Supports both CUDA (GPU) and CPU-only builds
#
# Build examples:
#   docker build -f docker/tts.Dockerfile --target cuda -t agent-cli-tts:cuda .
#   docker build -f docker/tts.Dockerfile --target cpu -t agent-cli-tts:cpu .
#
# Run examples:
#   docker run -p 10200:10200 -p 10201:10201 --gpus all agent-cli-tts:cuda
#   docker run -p 10200:10200 -p 10201:10201 agent-cli-tts:cpu

# =============================================================================
# CUDA target: GPU-accelerated with Kokoro TTS
# =============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu22.04 AS cuda

# Install system dependencies
# espeak-ng is required for Kokoro's phoneme generation
# build-essential is required for compiling C++ extensions (curated-tokenizers)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        git \
        ca-certificates \
        espeak-ng \
        libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user with explicit UID:GID 1000:1000
RUN groupadd -g 1000 tts && useradd -m -u 1000 -g tts tts

WORKDIR /app

# Install from lock file for reproducible builds
COPY pyproject.toml uv.lock ./
ENV UV_PYTHON=3.13
RUN uv sync --frozen --no-dev --extra kokoro --no-install-project && \
    ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli && \
    /app/.venv/bin/python -m spacy download en_core_web_sm

# Create cache directory for models
RUN mkdir -p /home/tts/.cache && chown -R tts:tts /home/tts

USER tts

# Expose ports: Wyoming (10200) and HTTP API (10201)
EXPOSE 10200 10201

# Default environment variables
ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=10201 \
    TTS_WYOMING_PORT=10200 \
    TTS_MODEL=kokoro \
    TTS_BACKEND=kokoro \
    TTS_TTL=300 \
    TTS_LOG_LEVEL=info \
    TTS_DEVICE=cuda

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${TTS_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server tts \
    --host ${TTS_HOST} \
    --port ${TTS_PORT} \
    --wyoming-port ${TTS_WYOMING_PORT} \
    --model ${TTS_MODEL} \
    --backend ${TTS_BACKEND} \
    --ttl ${TTS_TTL} \
    --device ${TTS_DEVICE} \
    --log-level ${TTS_LOG_LEVEL} \
    ${TTS_EXTRA_ARGS:-}"]

# =============================================================================
# CPU target: CPU-only with Piper TTS
# =============================================================================
FROM python:3.13-slim AS cpu

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user with explicit UID:GID 1000:1000
RUN groupadd -g 1000 tts && useradd -m -u 1000 -g tts tts

WORKDIR /app

# Install from lock file for reproducible builds
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra piper --no-install-project && \
    ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli

# Create cache directory for models
RUN mkdir -p /home/tts/.cache && chown -R tts:tts /home/tts

USER tts

# Expose ports: Wyoming (10200) and HTTP API (10201)
EXPOSE 10200 10201

# Default environment variables
ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=10201 \
    TTS_WYOMING_PORT=10200 \
    TTS_MODEL=en_US-lessac-medium \
    TTS_BACKEND=piper \
    TTS_TTL=300 \
    TTS_LOG_LEVEL=info \
    TTS_DEVICE=cpu

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${TTS_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server tts \
    --host ${TTS_HOST} \
    --port ${TTS_PORT} \
    --wyoming-port ${TTS_WYOMING_PORT} \
    --model ${TTS_MODEL} \
    --backend ${TTS_BACKEND} \
    --ttl ${TTS_TTL} \
    --device ${TTS_DEVICE} \
    --log-level ${TTS_LOG_LEVEL} \
    ${TTS_EXTRA_ARGS:-}"]
