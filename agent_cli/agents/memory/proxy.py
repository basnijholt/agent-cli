"""Memory Proxy agent command (long-term memory with Chroma)."""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003

import typer
from rich.logging import RichHandler

from agent_cli import constants, opts
from agent_cli.agents.memory import memory_app
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import console, print_command_line_args


@memory_app.command("proxy")
@requires_extras("memory")
def proxy(
    memory_path: Path = typer.Option(  # noqa: B008
        "./memory_db",
        help="Directory for memory storage. Contains `entries/` (Markdown files) and `chroma/` (vector index). Created automatically if it doesn't exist.",
        rich_help_panel="Memory Configuration",
    ),
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    embedding_model: str = opts.EMBEDDING_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    default_top_k: int = typer.Option(
        5,
        help="Number of relevant memories to inject into each request. Higher values provide more context but increase token usage.",
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
        help="Maximum entries per conversation before oldest are evicted. Summaries are preserved separately.",
        rich_help_panel="Memory Configuration",
    ),
    mmr_lambda: float = typer.Option(
        0.7,
        help="MMR lambda (0-1): higher favors relevance, lower favors diversity.",
        rich_help_panel="Memory Configuration",
    ),
    recency_weight: float = typer.Option(
        0.2,
        help="Weight for recency vs semantic relevance (0.0-1.0). At 0.2: 20% recency, 80% semantic similarity.",
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
        help="Extract facts and generate summaries after each turn using the LLM. Disable to only store raw conversation turns.",
        rich_help_panel="Memory Configuration",
    ),
    git_versioning: bool = typer.Option(
        True,  # noqa: FBT003
        "--git-versioning/--no-git-versioning",
        help="Auto-commit memory changes to git. Initializes a repo in `--memory-path` if needed. Provides full history of memory evolution.",
        rich_help_panel="Memory Configuration",
    ),
    log_level: opts.LogLevel = opts.SERVER_LOG_LEVEL,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Start the memory-backed chat proxy server.

    This server acts as a middleware between your chat client (e.g., a web UI,
    CLI, or IDE plugin) and an OpenAI-compatible LLM provider (e.g., OpenAI,
    Ollama, vLLM).

    **Key Features:**

    - **Simple Markdown Files:** Memories are stored as human-readable Markdown
      files, serving as the ultimate source of truth.
    - **Automatic Version Control:** Built-in Git integration automatically
      commits changes, providing a full history of memory evolution.
    - **Lightweight & Local:** Minimal dependencies and runs entirely on your
      machine.
    - **Proxy Middleware:** Works transparently with any OpenAI-compatible
      `/chat/completions` endpoint.

    **How it works:**

    1.  Intercepts `POST /v1/chat/completions` requests.
    2.  **Retrieves** relevant memories (facts, previous conversations) from a
        local vector database (ChromaDB) based on the user's query.
    3.  **Injects** these memories into the system prompt.
    4.  **Forwards** the augmented request to the real LLM (`--openai-base-url`).
    5.  **Extracts** new facts from the conversation in the background and
        updates the long-term memory store (including handling contradictions).

    **Example:**

        # Start proxy pointing to local Ollama
        agent-cli memory proxy --openai-base-url http://localhost:11434/v1

        # Then configure your chat client to use http://localhost:8100/v1
        # as its OpenAI base URL. All requests flow through the memory proxy.

    **Per-request overrides:** Clients can include these fields in the request
    body: `memory_id` (conversation ID), `memory_top_k`, `memory_recency_weight`,
    `memory_score_threshold`.
    """
    if print_args:
        print_command_line_args(locals())

    import uvicorn  # noqa: PLC0415

    from agent_cli.memory._files import ensure_store_dirs  # noqa: PLC0415
    from agent_cli.memory.api import create_app  # noqa: PLC0415

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
