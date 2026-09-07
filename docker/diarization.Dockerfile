# Transcription proxy with local speaker diarization (CPU or NVIDIA GPU).
# docker build -f docker/diarization.Dockerfile -t agent-cli-diarization .
# docker run --rm -p 61337:61337 -e HF_TOKEN agent-cli-diarization
# Add --gpus all -e DIARIZATION_DEVICE=cuda to use an NVIDIA GPU.
FROM python:3.13-slim-bookworm AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
    --extra server --extra wyoming --extra llm --extra diarization
COPY .git ./.git
COPY agent_cli ./agent_cli
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable \
    --extra server --extra wyoming --extra llm --extra diarization

FROM python:3.13-slim-bookworm

# PyTorch wheels include CUDA libraries and also support CPU inference.
# FFmpeg shared libraries are needed by torchcodec, as well as audio conversion.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g 1000 transcribe && useradd -m -u 1000 -g 1000 transcribe
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /bin/uv /bin/uvx /bin/
RUN ln -s /app/.venv/bin/agent-cli /usr/local/bin/agent-cli && \
    mkdir -p /home/transcribe/.cache && chown -R transcribe:transcribe /home/transcribe
USER transcribe
EXPOSE 61337
ENV PROXY_HOST=0.0.0.0 \
    PROXY_PORT=61337 \
    DIARIZATION_DEVICE=auto
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['PROXY_PORT'] + '/health')" || exit 1
ENTRYPOINT ["sh", "-c", "exec agent-cli server transcribe-proxy --host \"${PROXY_HOST}\" --port \"${PROXY_PORT}\" ${PROXY_EXTRA_ARGS:-}"]
