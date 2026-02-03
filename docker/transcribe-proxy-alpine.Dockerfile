# Dockerfile for agent-cli Transcription Proxy server (Alpine)
# Experimental lightweight build using Alpine Linux

FROM python:3.13-alpine AS builder

RUN apk add --no-cache git

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --no-editable --extra server --extra wyoming --extra llm-core

# =============================================================================
# Runtime stage
# =============================================================================
FROM python:3.13-alpine

RUN apk add --no-cache ffmpeg

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN addgroup -g 1000 transcribe && adduser -u 1000 -G transcribe -D transcribe

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

RUN ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli

USER transcribe

EXPOSE 61337

ENV PROXY_HOST=0.0.0.0 \
    PROXY_PORT=61337

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PROXY_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli server transcribe-proxy \
    --host ${PROXY_HOST} \
    --port ${PROXY_PORT} \
    ${PROXY_EXTRA_ARGS:-}"]
