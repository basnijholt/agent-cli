# Dockerfile for agent-cli Memory Proxy server
# A long-term memory proxy that stores facts and injects relevant context into LLM requests
#
# Build example:
#   docker build -f docker/memory-proxy.Dockerfile -t agent-cli-memory-proxy .
#
# Run examples:
#   docker run -p 8100:8100 -v ./memory:/data/memory agent-cli-memory-proxy
#
#   # With custom OpenAI-compatible backend:
#   docker run -p 8100:8100 \
#     -v ./memory:/data/memory \
#     -e OPENAI_BASE_URL=http://ollama:11434/v1 \
#     agent-cli-memory-proxy
#
# Environment variables (priority: env var > config file > default):
#   MEMORY_PATH          - Directory for memory storage (default: /data/memory)
#   MEMORY_TOP_K         - Number of memories to retrieve per query (default: 5)
#   MEMORY_MAX_ENTRIES   - Max entries per conversation before eviction (default: 500)
#   MEMORY_MMR_LAMBDA    - MMR lambda 0-1, higher=relevance (default: 0.7)
#   MEMORY_RECENCY_WEIGHT - Weight for recency vs semantic (default: 0.2)
#   MEMORY_SCORE_THRESHOLD - Min relevance threshold (default: 0.35)
#   MEMORY_SUMMARIZATION - Enable fact extraction: true/false (default: true)
#   MEMORY_GIT_VERSIONING - Enable git versioning: true/false (default: true)
#   EMBEDDING_MODEL      - Embedding model name (default: text-embedding-3-small)
#   OPENAI_BASE_URL      - OpenAI-compatible API base URL
#   OPENAI_API_KEY       - API key for embeddings and chat
#   MEMORY_HOST          - Server bind address (default: 0.0.0.0)
#   MEMORY_PORT          - Server port (default: 8100)
#   LOG_LEVEL            - Logging level: debug, info, warning, error (default: info)

# =============================================================================
# Builder stage - install dependencies and project
# =============================================================================
FROM python:3.14-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN uv sync --frozen --no-dev --no-editable --extra memory

# =============================================================================
# Runtime stage - minimal image using Python slim directly
# =============================================================================
FROM python:3.14-slim

# Install runtime dependencies:
# - libgomp1: Required by onnxruntime for parallel processing
# - git: Required for memory git versioning feature
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 memory && useradd -m -u 1000 -g memory memory

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

RUN ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli

# Create data directory
RUN mkdir -p /data/memory && chown -R memory:memory /data

USER memory

# Configure git for memory versioning (required for commits)
RUN git config --global user.email "memory-proxy@agent-cli.local" && \
    git config --global user.name "Memory Proxy"

# Cache directory for models (embeddings)
ENV HF_HOME=/home/memory/.cache/huggingface
RUN mkdir -p /home/memory/.cache/huggingface

EXPOSE 8100

ENV MEMORY_HOST=0.0.0.0 \
    MEMORY_PORT=8100 \
    MEMORY_PATH=/data/memory \
    MEMORY_TOP_K=5 \
    MEMORY_MAX_ENTRIES=500 \
    MEMORY_MMR_LAMBDA=0.7 \
    MEMORY_RECENCY_WEIGHT=0.2 \
    MEMORY_SCORE_THRESHOLD=0.35 \
    MEMORY_SUMMARIZATION=true \
    MEMORY_GIT_VERSIONING=true \
    EMBEDDING_MODEL=text-embedding-3-small \
    LOG_LEVEL=info

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${MEMORY_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli memory proxy \
    --host ${MEMORY_HOST} \
    --port ${MEMORY_PORT} \
    --memory-path ${MEMORY_PATH} \
    --default-top-k ${MEMORY_TOP_K} \
    --max-entries ${MEMORY_MAX_ENTRIES} \
    --mmr-lambda ${MEMORY_MMR_LAMBDA} \
    --recency-weight ${MEMORY_RECENCY_WEIGHT} \
    --score-threshold ${MEMORY_SCORE_THRESHOLD} \
    --embedding-model ${EMBEDDING_MODEL} \
    --log-level ${LOG_LEVEL} \
    $([ \"${MEMORY_SUMMARIZATION}\" = \"false\" ] && echo '--no-summarization' || echo '--summarization') \
    $([ \"${MEMORY_GIT_VERSIONING}\" = \"false\" ] && echo '--no-git-versioning' || echo '--git-versioning') \
    ${MEMORY_EXTRA_ARGS:-}"]
