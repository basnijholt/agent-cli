# Dockerfile for agent-cli Transcription Proxy server
# A lightweight proxy that forwards requests to configured ASR providers
#
# Build example:
#   docker build -f docker/transcription-proxy.Dockerfile -t agent-cli-transcription-proxy .
#
# Run example:
#   docker run -p 61337:61337 agent-cli-transcription-proxy

FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user with explicit UID:GID 1000:1000
RUN groupadd -g 1000 proxy && useradd -m -u 1000 -g proxy proxy

WORKDIR /app

# Install agent-cli with server support
ENV UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv-tools

# --refresh bypasses uv cache to ensure latest version from PyPI
RUN uv tool install --refresh "agent-cli[server]"

USER proxy

# Expose port
EXPOSE 61337

# Default environment variables
ENV PROXY_HOST=0.0.0.0 \
    PROXY_PORT=61337

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PROXY_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server transcription-proxy \
    --host ${PROXY_HOST} \
    --port ${PROXY_PORT} \
    ${PROXY_EXTRA_ARGS:-}"]
