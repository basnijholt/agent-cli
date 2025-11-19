"""RAG Server agent command."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path  # noqa: TC003

import typer

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message

has_fastapi = find_spec("fastapi") is not None
has_uvicorn = find_spec("uvicorn") is not None
has_chromadb = find_spec("chromadb") is not None
has_watchfiles = find_spec("watchfiles") is not None
has_sentence_transformers = find_spec("sentence_transformers") is not None


@app.command("rag-server")
def rag_server(
    docs_folder: Path = typer.Option(  # noqa: B008
        "./rag_docs",
        help="Folder to watch for documents",
    ),
    chroma_path: Path = typer.Option(  # noqa: B008
        "./rag_db",
        help="Path to ChromaDB persistence directory",
    ),
    llama_url: str = typer.Option(
        "http://localhost:8080",
        help="URL of the llama.cpp server",
    ),
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),  # noqa: S104
    port: int = typer.Option(8000, help="Port to bind to"),
) -> None:
    """Start the RAG (Retrieval-Augmented Generation) Proxy Server.

    This server watches a folder for documents, indexes them, and provides
    an OpenAI-compatible API that proxies requests to a backend LLM (like llama.cpp),
    injecting relevant context from the documents.
    """
    if not (
        has_fastapi
        and has_uvicorn
        and has_chromadb
        and has_watchfiles
        and has_sentence_transformers
    ):
        msg = "RAG dependencies are not installed. Please install with `pip install agent-cli[rag]` or `uv sync --extra rag`."
        print_error_message(msg)
        raise typer.Exit(1)

    import uvicorn  # noqa: PLC0415

    from agent_cli.rag.api import create_app  # noqa: PLC0415

    console.print(f"[bold green]Starting RAG Server on {host}:{port}[/bold green]")
    console.print(f"  📂 Docs: [blue]{docs_folder}[/blue]")
    console.print(f"  💾 DB: [blue]{chroma_path}[/blue]")
    console.print(f"  🦙 Llama: [blue]{llama_url}[/blue]")

    fastapi_app = create_app(docs_folder, chroma_path, llama_url)

    uvicorn.run(fastapi_app, host=host, port=port)
