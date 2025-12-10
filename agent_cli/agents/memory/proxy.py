"""Memory Proxy agent command (long-term memory with Chroma)."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003

import typer
from rich.logging import RichHandler

from agent_cli import constants, opts
from agent_cli.agents.memory import memory_app
from agent_cli.core.utils import console, print_command_line_args, print_error_message


@memory_app.command("proxy")
def proxy(
    memory_path: Path = typer.Option(  # noqa: B008
        "./memory_db",
        help="Path to the memory store (files + derived vector index).",
        rich_help_panel="Memory Configuration",
    ),
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    embedding_model: str = opts.EMBEDDING_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    default_top_k: int = typer.Option(
        5,
        help="Number of memory entries to retrieve per query.",
        rich_help_panel="Memory Configuration",
    ),
    host: str = opts.SERVER_HOST,
    port: int = typer.Option(
        8100,
        help="Port to bind to",
        rich_help_panel="Server Configuration",
    ),
    max_entries: int = typer.Option(
        500,
        help="Maximum stored memory entries per conversation (excluding summary).",
        rich_help_panel="Memory Configuration",
    ),
    mmr_lambda: float = typer.Option(
        0.7,
        help="MMR lambda (0-1): higher favors relevance, lower favors diversity.",
        rich_help_panel="Memory Configuration",
    ),
    recency_weight: float = typer.Option(
        0.2,
        help="Recency score weight (0.0-1.0). Controls freshness vs. relevance. Default 0.2 (20% recency, 80% semantic relevance).",
        rich_help_panel="Memory Configuration",
    ),
    score_threshold: float = typer.Option(
        0.35,
        help="Minimum semantic relevance threshold (0.0-1.0). Memories below this score are discarded to reduce noise.",
        rich_help_panel="Memory Configuration",
    ),
    summarization: bool = typer.Option(
        True,  # noqa: FBT003
        "--summarization/--no-summarization",
        help="Enable automatic fact extraction and summaries.",
        rich_help_panel="Memory Configuration",
    ),
    git_versioning: bool = typer.Option(
        True,  # noqa: FBT003
        "--git-versioning/--no-git-versioning",
        help="Enable automatic git commit of memory changes.",
        rich_help_panel="Memory Configuration",
    ),
    log_level: str = opts.with_default(opts.LOG_LEVEL, "INFO"),
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Start the memory-backed chat proxy server.

    This server acts as a middleware between your chat client (e.g., a web UI,
    CLI, or IDE plugin) and an OpenAI-compatible LLM provider (e.g., OpenAI,
    Ollama, vLLM).

    Key Features:

    - **Simple Markdown Files:** Memories are stored as human-readable Markdown
      files, serving as the ultimate source of truth.
    - **Automatic Version Control:** Built-in Git integration automatically
      commits changes, providing a full history of memory evolution.
    - **Lightweight & Local:** Minimal dependencies and runs entirely on your
      machine.
    - **Proxy Middleware:** Works transparently with any OpenAI-compatible
      `/chat/completions` endpoint.

    How it works:

    1.  Intercepts `POST /v1/chat/completions` requests.
    2.  **Retrieves** relevant memories (facts, previous conversations) from a
        local vector database (ChromaDB) based on the user's query.
    3.  **Injects** these memories into the system prompt.
    4.  **Forwards** the augmented request to the real LLM (`--openai-base-url`).
    5.  **Extracts** new facts from the conversation in the background and
        updates the long-term memory store (including handling contradictions).

    Use this to give "long-term memory" to any OpenAI-compatible application.
    Point your client's base URL to `http://localhost:8100/v1`.
    """
    if print_args:
        print_command_line_args(locals())

    try:
        import uvicorn  # noqa: PLC0415

        from agent_cli.memory._files import ensure_store_dirs  # noqa: PLC0415
        from agent_cli.memory.api import create_app  # noqa: PLC0415
    except ImportError as exc:
        print_error_message(
            "Memory dependencies are not installed. Please install with "
            "`pip install agent-cli[memory]` or `uv sync --extra memory`.",
        )
        raise typer.Exit(1) from exc

    logging.basicConfig(
        level=log_level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    memory_path = memory_path.resolve()
    entries_dir, _ = ensure_store_dirs(memory_path)
    if openai_base_url is None:
        openai_base_url = constants.DEFAULT_OPENAI_BASE_URL

    console.print(f"[bold green]Starting Memory Proxy on {host}:{port}[/bold green]")
    console.print(f"  💾 Memory store: [blue]{memory_path}[/blue]")
    console.print(f"  📁 Entries: [blue]{entries_dir}[/blue]")
    console.print(f"  🤖 Backend: [blue]{openai_base_url}[/blue]")
    console.print(f"  🧠 Embeddings: Using [blue]{embedding_model}[/blue]")
    console.print(f"  🔍 Memory top_k: [blue]{default_top_k}[/blue] entries per query")
    console.print(f"  🧹 Max entries per conversation: [blue]{max_entries}[/blue]")
    console.print(
        f"  ⚖️  Scoring: MMR λ=[blue]{mmr_lambda}[/blue], Recency w=[blue]{recency_weight}[/blue], Threshold=[blue]{score_threshold}[/blue]",
    )
    if not summarization:
        console.print("  ⚙️  Summaries: [red]disabled[/red]")
    if git_versioning:
        console.print("  📝 Git Versioning: [green]enabled[/green]")

    fastapi_app = create_app(
        memory_path,
        openai_base_url,
        embedding_model=embedding_model,
        embedding_api_key=openai_api_key,
        chat_api_key=openai_api_key,
        default_top_k=default_top_k,
        enable_summarization=summarization,
        max_entries=max_entries,
        mmr_lambda=mmr_lambda,
        recency_weight=recency_weight,
        score_threshold=score_threshold,
        enable_git_versioning=git_versioning,
    )

    uvicorn.run(fastapi_app, host=host, port=port, log_config=None)
