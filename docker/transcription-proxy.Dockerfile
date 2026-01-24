# syntax=docker/dockerfile:1
# Dockerfile for agent-cli Transcription Proxy server
# A lightweight proxy that forwards requests to configured ASR providers
#
# Build example:
#   docker build -f docker/transcription-proxy.Dockerfile -t agent-cli-transcription-proxy .
#
# Run example:
#   docker run -p 61337:61337 agent-cli-transcription-proxy

# Build stage - install with uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# --refresh bypasses uv cache to ensure latest version from PyPI
RUN uv tool install --refresh --compile-bytecode "agent-cli[server]"

# Runtime stage - minimal image without uv
FROM python:3.13-slim

# Create non-root user with explicit UID:GID 1000:1000
RUN groupadd -g 1000 transcribe && useradd -m -u 1000 -g transcribe transcribe

# Copy installed tool virtualenv from builder (keep original path for shebang compatibility)
COPY --from=builder /root/.local/share/uv/tools/agent-cli /root/.local/share/uv/tools/agent-cli

# Make tool accessible to non-root users and create symlinks
RUN chmod 755 /root /root/.local /root/.local/share /root/.local/share/uv /root/.local/share/uv/tools && \
    chmod -R 755 /root/.local/share/uv/tools/agent-cli && \
    ln -s /root/.local/share/uv/tools/agent-cli/bin/agent-cli /usr/local/bin/agent-cli && \
    ln -s /root/.local/share/uv/tools/agent-cli/bin/agent /usr/local/bin/agent && \
    ln -s /root/.local/share/uv/tools/agent-cli/bin/ag /usr/local/bin/ag

USER transcribe

WORKDIR /app

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
