# Dockerfile for agent-cli RAG Proxy server
# A document-aware proxy that indexes files and injects relevant context into LLM requests
#
# Build example:
#   docker build -f docker/rag-proxy.Dockerfile -t agent-cli-rag-proxy .
#
# Run examples:
#   docker run -p 8000:8000 -v ./docs:/data/docs agent-cli-rag-proxy
#
#   # With custom OpenAI-compatible backend:
#   docker run -p 8000:8000 \
#     -v ./docs:/data/docs \
#     -v ./rag_db:/data/db \
#     -e OPENAI_BASE_URL=http://ollama:11434/v1 \
#     agent-cli-rag-proxy
#
# Environment variables (priority: env var > config file > default):
#   RAG_DOCS_FOLDER      - Folder to watch for documents (default: /data/docs)
#   RAG_CHROMA_PATH      - ChromaDB storage directory (default: /data/db)
#   RAG_LIMIT            - Number of chunks to retrieve per query (default: 3)
#   RAG_ENABLE_TOOLS     - Enable read_full_document tool: true/false (default: true)
#   EMBEDDING_MODEL      - Embedding model name (default: text-embedding-3-small)
#   OPENAI_BASE_URL      - OpenAI-compatible API base URL
#   OPENAI_API_KEY       - API key for embeddings and chat
#   RAG_HOST             - Server bind address (default: 0.0.0.0)
#   RAG_PORT             - Server port (default: 8000)
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
RUN uv sync --frozen --no-dev --no-editable --extra rag

# =============================================================================
# Runtime stage - minimal image using Python slim directly
# =============================================================================
FROM python:3.14-slim

# Install runtime dependencies:
# - libgomp1: Required by onnxruntime for parallel processing
# - git: Required for .git detection in some document types
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 rag && useradd -m -u 1000 -g rag rag

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

RUN ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli

# Create data directories
RUN mkdir -p /data/docs /data/db && chown -R rag:rag /data

USER rag

# Cache directory for models (embeddings, reranker)
ENV HF_HOME=/home/rag/.cache/huggingface
RUN mkdir -p /home/rag/.cache/huggingface

EXPOSE 8000

ENV RAG_HOST=0.0.0.0 \
    RAG_PORT=8000 \
    RAG_DOCS_FOLDER=/data/docs \
    RAG_CHROMA_PATH=/data/db \
    RAG_LIMIT=3 \
    RAG_ENABLE_TOOLS=true \
    EMBEDDING_MODEL=text-embedding-3-small \
    LOG_LEVEL=info

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${RAG_PORT}/health')" || exit 1

ENTRYPOINT ["sh", "-c", "agent-cli rag-proxy \
    --host ${RAG_HOST} \
    --port ${RAG_PORT} \
    --docs-folder ${RAG_DOCS_FOLDER} \
    --chroma-path ${RAG_CHROMA_PATH} \
    --limit ${RAG_LIMIT} \
    --embedding-model ${EMBEDDING_MODEL} \
    --log-level ${LOG_LEVEL} \
    $([ \"${RAG_ENABLE_TOOLS}\" = \"false\" ] && echo '--no-rag-tools' || echo '--rag-tools') \
    ${RAG_EXTRA_ARGS:-}"]
