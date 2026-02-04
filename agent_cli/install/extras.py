"""Install optional extras at runtime with pinned versions."""

from __future__ import annotations

from typing import Annotated

import typer

from agent_cli.cli import app
from agent_cli.core.deps import (
    EXTRAS as _EXTRAS_META,
)
from agent_cli.core.deps import (
    available_extras,
    install_extras_impl,
    is_uv_tool_install,
)
from agent_cli.core.utils import console, print_error_message

# Extract descriptions from the centralized EXTRAS metadata
EXTRAS: dict[str, str] = {name: desc for name, (desc, _) in _EXTRAS_META.items()}


@app.command("install-extras", rich_help_panel="Installation", no_args_is_help=True)
def install_extras(
    extras: Annotated[
        list[str] | None,
        typer.Argument(
            help="Extras to install: `audio`, `faster-whisper`, `kokoro`, `llm`, `memory`, "
            "`mlx-whisper`, `piper`, `rag`, `server`, `speed`, `vad`, `whisper-transformers`, "
            "`wyoming`",
        ),
    ] = None,
    list_extras: Annotated[
        bool,
        typer.Option(
            "--list",
            "-l",
            help="Show available extras with descriptions (what each one enables)",
        ),
    ] = False,
    all_extras: Annotated[
        bool,
        typer.Option("--all", "-a", help="Install all available extras at once"),
    ] = False,
) -> None:
    """Install optional dependencies with pinned, compatible versions.

    Many agent-cli features require optional dependencies. This command installs
    them with version pinning to ensure compatibility. Dependencies persist
    across `uv tool upgrade` when installed via `uv tool`.

    **Available extras:**
    - `audio` - Audio recording/playback
    - `faster-whisper` - Whisper ASR via CTranslate2
    - `kokoro` - Kokoro neural TTS (GPU)
    - `llm` - LLM framework (pydantic-ai)
    - `memory` - Long-term memory proxy
    - `mlx-whisper` - Whisper ASR for Apple Silicon
    - `piper` - Piper TTS (CPU)
    - `rag` - RAG proxy (ChromaDB, embeddings)
    - `server` - FastAPI server components
    - `speed` - Audio speed adjustment (audiostretchy)
    - `vad` - Voice Activity Detection (Silero VAD via ONNX)
    - `whisper-transformers` - Whisper ASR via HuggingFace transformers
    - `wyoming` - Wyoming protocol support

    **Examples:**

        agent-cli install-extras rag           # Install RAG dependencies
        agent-cli install-extras memory vad    # Install multiple extras
        agent-cli install-extras --list        # Show available extras
        agent-cli install-extras --all         # Install all extras

    """
    available = available_extras()

    if list_extras:
        console.print("[bold]Available extras:[/]")
        for name in available:
            desc = EXTRAS.get(name, "")
            console.print(f"  [cyan]{name}[/]: {desc}")
        return

    if all_extras:
        extras = available

    if not extras:
        print_error_message("No extras specified. Use --list to see available, or --all.")
        raise typer.Exit(1)

    invalid = [e for e in extras if e not in available]
    if invalid:
        print_error_message(f"Unknown extras: {invalid}. Use --list to see available.")
        raise typer.Exit(1)

    if not install_extras_impl(extras):
        print_error_message("Failed to install extras")
        raise typer.Exit(1)

    if is_uv_tool_install():
        console.print("[green]Done! Extras will persist across uv tool upgrade.[/]")
    else:
        console.print("[green]Done![/]")
