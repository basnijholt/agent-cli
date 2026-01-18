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
# CUDA target: GPU-accelerated with faster-whisper
# =============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu22.04 AS cuda

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ffmpeg \
        git \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user with explicit UID:GID 1000:1000
RUN groupadd -g 1000 whisper && useradd -m -u 1000 -g whisper whisper

WORKDIR /app

# Install Python 3.13 and agent-cli with whisper support using uv tool
# UV_PYTHON_INSTALL_DIR ensures Python is installed in accessible location (not /root/.local/)
ENV UV_PYTHON=3.13 \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv-tools \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python

# VERSION can be passed as build arg to pin exact version (e.g., "0.61.3")
# If empty, installs latest version from PyPI
ARG VERSION
RUN if [ -n "$VERSION" ]; then \
      uv tool install --refresh --python 3.13 "agent-cli[whisper]==${VERSION}"; \
    else \
      uv tool install --refresh --python 3.13 "agent-cli[whisper]"; \
    fi

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
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${WHISPER_PORT}/health')" || exit 1

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
RUN groupadd -g 1000 whisper && useradd -m -u 1000 -g whisper whisper

WORKDIR /app

# Install agent-cli with whisper support
ENV UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv-tools

# VERSION can be passed as build arg to pin exact version (e.g., "0.61.3")
# If empty, installs latest version from PyPI
ARG VERSION
RUN if [ -n "$VERSION" ]; then \
      uv tool install --refresh "agent-cli[whisper]==${VERSION}"; \
    else \
      uv tool install --refresh "agent-cli[whisper]"; \
    fi

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
    WHISPER_DEVICE=cpu

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
