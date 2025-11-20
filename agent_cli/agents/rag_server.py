"""RAG Server agent command."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003

import typer
from rich.logging import RichHandler

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message


@app.command("rag-server")
def rag_server(
    docs_folder: Path = typer.Option(  # noqa: B008
        "./rag_docs",
        help="Folder to watch for documents",
        rich_help_panel="RAG Configuration",
    ),
    chroma_path: Path = typer.Option(  # noqa: B008
        "./rag_db",
        help="Path to ChromaDB persistence directory",
        rich_help_panel="RAG Configuration",
    ),
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    embedding_model: str = typer.Option(
        "text-embedding-3-small",
        help="Embedding model name (e.g. 'text-embedding-3-small' for OpenAI).",
        rich_help_panel="Backend Configuration",
    ),
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    limit: int = typer.Option(
        3,
        help="Number of document chunks to retrieve per query.",
        rich_help_panel="RAG Configuration",
    ),
    host: str = typer.Option(
        "0.0.0.0",  # noqa: S104
        help="Host to bind to",
        rich_help_panel="Server Configuration",
    ),
    port: int = typer.Option(
        8000,
        help="Port to bind to",
        rich_help_panel="Server Configuration",
    ),
    log_level: str = typer.Option(
        "INFO",
        help="Logging level",
        rich_help_panel="General Options",
    ),
) -> None:
    """Start the RAG (Retrieval-Augmented Generation) Proxy Server.

    This server watches a folder for documents, indexes them, and provides
    an OpenAI-compatible API that proxies requests to a backend LLM (like llama.cpp),
    injecting relevant context from the documents.
    """
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

    try:
        import uvicorn  # noqa: PLC0415

        from agent_cli.rag.api import create_app  # noqa: PLC0415
    except ImportError as exc:
        print_error_message(
            "RAG dependencies are not installed. Please install with "
            "`pip install agent-cli[rag]` or `uv sync --extra rag`.",
        )
        raise typer.Exit(1) from exc

    docs_folder = docs_folder.resolve()
    chroma_path = chroma_path.resolve()
    if openai_base_url is None:
        openai_base_url = "https://api.openai.com/v1"

    console.print(f"[bold green]Starting RAG Server on {host}:{port}[/bold green]")
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
    )

    uvicorn.run(fastapi_app, host=host, port=port, log_config=None)
