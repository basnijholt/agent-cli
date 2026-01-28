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
# Builder stage for CUDA - Kokoro TTS (requires build tools)
# =============================================================================
FROM python:3.13-slim AS builder-cuda

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --no-editable --extra server --extra kokoro --extra wyoming && \
    /app/.venv/bin/python -m spacy download en_core_web_sm

# =============================================================================
# Builder stage for CPU - Piper TTS
# =============================================================================
FROM python:3.13-slim AS builder-cpu

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --no-editable --extra server --extra piper --extra wyoming

# =============================================================================
# CUDA target: GPU-accelerated with Kokoro TTS
# =============================================================================
FROM nvcr.io/nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS cuda

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        espeak-ng \
        libsndfile1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.13

# Delete pre-existing ubuntu user (UID 1000) and create tts user for uniformity with CPU target
RUN userdel -r ubuntu && \
    groupadd -g 1000 tts && \
    useradd -m -u 1000 -g 1000 tts

WORKDIR /app

COPY --from=builder-cuda /app/.venv /app/.venv

RUN ln -sf $(uv python find 3.13) /app/.venv/bin/python && \
    ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli && \
    mkdir -p /home/tts/.cache && chown -R tts:tts /home/tts

USER tts

EXPOSE 10200 10201

ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=10201 \
    TTS_WYOMING_PORT=10200 \
    TTS_MODEL=kokoro \
    TTS_BACKEND=kokoro \
    TTS_TTL=300 \
    TTS_LOG_LEVEL=info \
    TTS_DEVICE=cuda

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:${TTS_PORT}/health')" || exit 1

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
FROM debian:bookworm-slim AS cpu

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.13

RUN getent group 1000 || groupadd -g 1000 tts; \
    id -u 1000 >/dev/null 2>&1 || useradd -m -u 1000 -g 1000 tts

WORKDIR /app

COPY --from=builder-cpu /app/.venv /app/.venv

RUN ln -sf $(uv python find 3.13) /app/.venv/bin/python && \
    ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli && \
    mkdir -p /home/tts/.cache && chown -R tts:tts /home/tts

USER tts

EXPOSE 10200 10201

ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=10201 \
    TTS_WYOMING_PORT=10200 \
    TTS_MODEL=en_US-lessac-medium \
    TTS_BACKEND=piper \
    TTS_TTL=300 \
    TTS_LOG_LEVEL=info \
    TTS_DEVICE=cpu

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:${TTS_PORT}/health')" || exit 1

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
