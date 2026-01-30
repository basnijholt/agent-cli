"""RAG Proxy agent command."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003

import typer
from rich.logging import RichHandler

from agent_cli import constants, opts
from agent_cli.cli import app
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_error_message,
)


@app.command("rag-proxy", rich_help_panel="Servers")
@requires_extras("rag")
def rag_proxy(
    docs_folder: Path = typer.Option(  # noqa: B008
        "./rag_docs",
        help="Folder to watch for documents. Files are auto-indexed on startup and when changed. Must not overlap with `--chroma-path`.",
        rich_help_panel="RAG Configuration",
    ),
    chroma_path: Path = typer.Option(  # noqa: B008
        "./rag_db",
        help="ChromaDB storage directory for vector embeddings. Must be separate from `--docs-folder` to avoid indexing database files.",
        rich_help_panel="RAG Configuration",
    ),
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    embedding_model: str = opts.EMBEDDING_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    limit: int = typer.Option(
        3,
        help="Number of document chunks to retrieve per query. Higher values provide more context but use more tokens. Can be overridden per-request via `rag_top_k` in the JSON body.",
        rich_help_panel="RAG Configuration",
    ),
    host: str = opts.SERVER_HOST,
    port: int = typer.Option(
        8000,
        help="Port for the RAG proxy API (e.g., `http://localhost:8000/v1/chat/completions`).",
        rich_help_panel="Server Configuration",
    ),
    log_level: opts.LogLevel = opts.SERVER_LOG_LEVEL,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
    enable_rag_tools: bool = typer.Option(
        True,  # noqa: FBT003
        "--rag-tools/--no-rag-tools",
        help="Enable `read_full_document()` tool so the LLM can request full document content when retrieved snippets are insufficient. Can be overridden per-request via `rag_enable_tools` in the JSON body.",
        rich_help_panel="RAG Configuration",
    ),
) -> None:
    """Start a RAG proxy server that enables "chat with your documents".

    Watches a folder for documents, indexes them into a vector store, and provides an
    OpenAI-compatible API at `/v1/chat/completions`. When you send a chat request,
    the server retrieves relevant document chunks and injects them as context before
    forwarding to your LLM backend.

    **Quick start:**

    - `agent-cli rag-proxy` — Start with defaults (./rag_docs, OpenAI-compatible API)
    - `agent-cli rag-proxy --docs-folder ~/notes` — Index your notes folder

    **How it works:**

    1. Documents in `--docs-folder` are chunked, embedded, and stored in ChromaDB
    2. A file watcher auto-reindexes when files change
    3. Chat requests trigger a semantic search for relevant chunks
    4. Retrieved context is injected into the prompt before forwarding to the LLM
    5. Responses include a `rag_sources` field listing which documents were used

    **Supported file formats:**

    Text: `.txt`, `.md`, `.json`, `.py`, `.js`, `.ts`, `.yaml`, `.toml`, `.rst`, etc.
    Rich documents (via MarkItDown): `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.csv`

    **API endpoints:**

    - `POST /v1/chat/completions` — Main chat endpoint (OpenAI-compatible)
    - `GET /health` — Health check with configuration info
    - `GET /files` — List indexed files with chunk counts
    - `POST /reindex` — Trigger manual reindex
    - All other paths are proxied to the LLM backend

    **Per-request overrides (in JSON body):**

    - `rag_top_k`: Override `--limit` for this request
    - `rag_enable_tools`: Override `--rag-tools` for this request
    """
    if print_args:
        print_command_line_args(locals())
    # Configure logging
    logging.basicConfig(
        level=log_level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
        force=True,
    )

    # Suppress noisy logs from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    import uvicorn  # noqa: PLC0415

    from agent_cli.rag.api import create_app  # noqa: PLC0415

    docs_folder = docs_folder.resolve()
    chroma_path = chroma_path.resolve()

    # Validate paths don't overlap - mixing docs and DB causes corruption
    if docs_folder == chroma_path:
        print_error_message(
            "docs-folder and chroma-path cannot be the same directory.\n"
            "ChromaDB creates internal files that would be indexed as documents.",
        )
        raise typer.Exit(1)
    if chroma_path in docs_folder.parents:
        print_error_message(
            f"docs-folder ({docs_folder}) is inside chroma-path ({chroma_path}).\n"
            "ChromaDB creates internal files that would be indexed as documents.",
        )
        raise typer.Exit(1)
    if docs_folder in chroma_path.parents:
        print_error_message(
            f"chroma-path ({chroma_path}) is inside docs-folder ({docs_folder}).\n"
            "ChromaDB files may be accidentally deleted when managing documents.",
        )
        raise typer.Exit(1)

    if openai_base_url is None:
        openai_base_url = constants.DEFAULT_OPENAI_BASE_URL

    console.print(f"[bold green]Starting RAG Proxy on {host}:{port}[/bold green]")
    console.print(f"  📂 Docs: [blue]{docs_folder}[/blue]")
    console.print(f"  💾 DB: [blue]{chroma_path}[/blue]")
    console.print(f"  🤖 Backend: [blue]{openai_base_url}[/blue]")
    console.print(f"  🧠 Embeddings: Using [blue]{embedding_model}[/blue]")
    console.print(f"  🔍 Limit: [blue]{limit}[/blue] chunks per query")

    fastapi_app = create_app(
        docs_folder,
        chroma_path,
        openai_base_url,
        embedding_model,
        openai_api_key,
        openai_api_key,
        limit,
        enable_rag_tools=enable_rag_tools,
    )

    uvicorn.run(fastapi_app, host=host, port=port, log_config=None)
