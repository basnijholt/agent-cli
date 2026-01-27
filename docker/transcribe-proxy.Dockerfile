# Dockerfile for agent-cli Transcription Proxy server
# A lightweight proxy that forwards requests to configured ASR providers
#
# Build example:
#   docker build -f docker/transcribe-proxy.Dockerfile -t agent-cli-transcribe-proxy .
#
# Run examples:
#   docker run -p 61337:61337 agent-cli-transcribe-proxy
#
#   # With Wyoming ASR pointing to another container:
#   docker run -p 61337:61337 \
#     -e ASR_WYOMING_IP=whisper-server \
#     -e ASR_WYOMING_PORT=10300 \
#     agent-cli-transcribe-proxy
#
# Environment variables (priority: env var > config file > default):
#   ASR_PROVIDER       - ASR provider: wyoming, openai, gemini (default: wyoming)
#   ASR_WYOMING_IP     - Wyoming server IP (default: localhost)
#   ASR_WYOMING_PORT   - Wyoming server port (default: 10300)
#   LLM_PROVIDER       - LLM provider: ollama, openai, gemini (default: openai)
#   OPENAI_API_KEY     - OpenAI API key
#   GEMINI_API_KEY     - Gemini API key

# =============================================================================
# Builder stage - install dependencies and project
# =============================================================================
FROM python:3.13-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --no-editable --extra server --extra wyoming --extra llm

# =============================================================================
# Runtime stage - minimal image
# =============================================================================
FROM debian:bookworm-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv python install 3.13

RUN groupadd -g 1000 transcribe && useradd -m -u 1000 -g transcribe transcribe

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

RUN ln -sf $(uv python find 3.13) /app/.venv/bin/python && \
    ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli

USER transcribe

EXPOSE 61337

ENV PROXY_HOST=0.0.0.0 \
    PROXY_PORT=61337

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PROXY_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server transcribe-proxy \
    --host ${PROXY_HOST} \
    --port ${PROXY_PORT} \
    ${PROXY_EXTRA_ARGS:-}"]
