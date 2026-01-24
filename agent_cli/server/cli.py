"""CLI commands for the server module."""

from __future__ import annotations

import asyncio
import logging
from importlib.util import find_spec
from pathlib import Path  # noqa: TC003 - Typer needs this at runtime
from typing import Annotated

import typer
from rich.console import Console

from agent_cli.cli import app as main_app
from agent_cli.core.deps import requires_extras
from agent_cli.core.process import set_process_title
from agent_cli.server.common import setup_rich_logging

console = Console()
err_console = Console(stderr=True)
logger = logging.getLogger(__name__)

# Check for optional dependencies
HAS_UVICORN = find_spec("uvicorn") is not None
HAS_FASTAPI = find_spec("fastapi") is not None
HAS_FASTER_WHISPER = find_spec("faster_whisper") is not None
HAS_MLX_WHISPER = find_spec("mlx_whisper") is not None
HAS_PIPER = find_spec("piper") is not None
HAS_KOKORO = find_spec("kokoro") is not None

app = typer.Typer(
    name="server",
    help="Run ASR/TTS servers (Whisper, TTS, or proxy mode).",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)
main_app.add_typer(app, name="server", rich_help_panel="Servers")


@app.callback()
def server_callback(ctx: typer.Context) -> None:
    """Server command group callback."""
    if ctx.invoked_subcommand is not None:
        # Update process title to include full path: server-{subcommand}
        set_process_title(f"server-{ctx.invoked_subcommand}")


def _check_server_deps() -> None:
    """Check that server dependencies are available."""
    if not HAS_UVICORN or not HAS_FASTAPI:
        err_console.print(
            "[bold red]Error:[/bold red] Server dependencies not installed. "
            "Run: [cyan]pip install agent-cli\\[server][/cyan] "
            "or [cyan]uv sync --extra server[/cyan]",
        )
        raise typer.Exit(1)


def _check_tts_deps(backend: str = "auto") -> None:
    """Check that TTS dependencies are available."""
    _check_server_deps()

    if backend == "kokoro":
        if not HAS_KOKORO:
            err_console.print(
                "[bold red]Error:[/bold red] Kokoro backend requires kokoro. "
                "Run: [cyan]pip install agent-cli\\[tts-kokoro][/cyan] "
                "or [cyan]uv sync --extra tts-kokoro[/cyan]",
            )
            raise typer.Exit(1)
        return

    if backend == "piper":
        if not HAS_PIPER:
            err_console.print(
                "[bold red]Error:[/bold red] Piper backend requires piper-tts. "
                "Run: [cyan]pip install agent-cli\\[tts][/cyan] "
                "or [cyan]uv sync --extra tts[/cyan]",
            )
            raise typer.Exit(1)
        return

    # For auto, check if either is available
    if not HAS_PIPER and not HAS_KOKORO:
        err_console.print(
            "[bold red]Error:[/bold red] No TTS backend available. "
            "Run: [cyan]pip install agent-cli\\[tts][/cyan] for Piper "
            "or [cyan]pip install agent-cli\\[tts-kokoro][/cyan] for Kokoro",
        )
        raise typer.Exit(1)


def _download_tts_models(
    backend: str,
    models: list[str],
    cache_dir: Path | None,
) -> None:
    """Download TTS models/voices without starting the server."""
    if backend == "kokoro":
        from agent_cli.server.tts.backends.base import (  # noqa: PLC0415
            get_backend_cache_dir,
        )
        from agent_cli.server.tts.backends.kokoro import (  # noqa: PLC0415
            DEFAULT_VOICE,
            _ensure_model,
            _ensure_voice,
        )

        download_dir = cache_dir or get_backend_cache_dir("kokoro")
        console.print("[bold]Downloading Kokoro model...[/bold]")
        _ensure_model(download_dir)
        console.print("  [green]✓[/green] Model ready")

        voices = [v for v in models if v != "kokoro"] or [DEFAULT_VOICE]
        for voice in voices:
            console.print(f"  Downloading voice [cyan]{voice}[/cyan]...")
            _ensure_voice(voice, download_dir)
        console.print("[bold green]Download complete![/bold green]")
        return

    # Piper backend
    from piper.download_voices import download_voice  # noqa: PLC0415

    from agent_cli.server.tts.backends.base import get_backend_cache_dir  # noqa: PLC0415

    download_dir = cache_dir or get_backend_cache_dir("piper")
    console.print("[bold]Downloading Piper model(s)...[/bold]")
    for model_name in models:
        console.print(f"  Downloading [cyan]{model_name}[/cyan]...")
        download_voice(model_name, download_dir)
    console.print("[bold green]Download complete![/bold green]")


def _check_whisper_deps(backend: str, *, download_only: bool = False) -> None:
    """Check that Whisper dependencies are available."""
    _check_server_deps()
    if download_only:
        if not HAS_FASTER_WHISPER:
            err_console.print(
                "[bold red]Error:[/bold red] faster-whisper is required for --download-only. "
                "Run: [cyan]pip install agent-cli\\[whisper][/cyan] "
                "or [cyan]uv sync --extra whisper[/cyan]",
            )
            raise typer.Exit(1)
        return

    if backend == "mlx":
        if not HAS_MLX_WHISPER:
            err_console.print(
                "[bold red]Error:[/bold red] MLX Whisper backend requires mlx-whisper. "
                "Run: [cyan]pip install mlx-whisper[/cyan]",
            )
            raise typer.Exit(1)
        return

    if not HAS_FASTER_WHISPER:
        err_console.print(
            "[bold red]Error:[/bold red] Whisper dependencies not installed. "
            "Run: [cyan]pip install agent-cli\\[whisper][/cyan] "
            "or [cyan]uv sync --extra whisper[/cyan]",
        )
        raise typer.Exit(1)


@app.command("whisper")
@requires_extras("server", "whisper")
def whisper_cmd(  # noqa: PLR0912, PLR0915
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help="Model name(s) to load (can specify multiple)",
        ),
    ] = None,
    default_model: Annotated[
        str | None,
        typer.Option(
            "--default-model",
            help="Default model when not specified in request",
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device",
            "-d",
            help="Device: auto, cuda, cuda:0, cpu",
        ),
    ] = "auto",
    compute_type: Annotated[
        str,
        typer.Option(
            "--compute-type",
            help="Compute type: auto, float16, int8, int8_float16",
        ),
    ] = "auto",
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Model cache directory",
        ),
    ] = None,
    ttl: Annotated[
        int,
        typer.Option(
            "--ttl",
            help="Seconds before unloading idle model",
        ),
    ] = 300,
    preload: Annotated[
        bool,
        typer.Option(
            "--preload",
            help="Load model(s) at startup and wait for completion",
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Host to bind the server to",
        ),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="HTTP API port",
        ),
    ] = 10301,
    wyoming_port: Annotated[
        int,
        typer.Option(
            "--wyoming-port",
            help="Wyoming protocol port",
        ),
    ] = 10300,
    no_wyoming: Annotated[
        bool,
        typer.Option(
            "--no-wyoming",
            help="Disable Wyoming server",
        ),
    ] = False,
    download_only: Annotated[
        bool,
        typer.Option(
            "--download-only",
            help="Download model(s) and exit without starting server",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level: debug, info, warning, error",
        ),
    ] = "info",
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Backend: auto (platform detection), faster-whisper, mlx",
        ),
    ] = "auto",
) -> None:
    """Run Whisper ASR server with TTL-based model unloading.

    The server provides:
    - OpenAI-compatible /v1/audio/transcriptions endpoint
    - Wyoming protocol for Home Assistant integration
    - WebSocket streaming at /v1/audio/transcriptions/stream

    Models are loaded lazily on first request and unloaded after being
    idle for the TTL duration, freeing VRAM for other applications.

    Examples:
        # Run with default large-v3 model
        agent-cli server whisper

        # Run with specific model and 10-minute TTL
        agent-cli server whisper --model large-v3 --ttl 600

        # Run multiple models with different configs
        agent-cli server whisper --model large-v3 --model small

        # Download model without starting server
        agent-cli server whisper --model large-v3 --download-only

    """
    # Setup Rich logging for consistent output
    setup_rich_logging(log_level, console=console)

    valid_backends = ("auto", "faster-whisper", "mlx")
    if backend not in valid_backends:
        err_console.print(
            f"[bold red]Error:[/bold red] --backend must be one of: {', '.join(valid_backends)}",
        )
        raise typer.Exit(1)

    resolved_backend = backend
    if backend == "auto" and not download_only:
        from agent_cli.server.whisper.backends import detect_backend  # noqa: PLC0415

        resolved_backend = detect_backend()

    _check_whisper_deps(resolved_backend, download_only=download_only)

    if backend == "auto" and not download_only:
        logger.info("Selected %s backend (auto-detected)", resolved_backend)

    from agent_cli.server.whisper.model_manager import WhisperModelConfig  # noqa: PLC0415
    from agent_cli.server.whisper.model_registry import create_whisper_registry  # noqa: PLC0415

    # Default model if none specified
    if model is None:
        model = ["large-v3"]

    # Validate default model against model list
    if default_model is not None and default_model not in model:
        err_console.print(
            f"[bold red]Error:[/bold red] --default-model '{default_model}' "
            f"is not in the model list: {model}",
        )
        raise typer.Exit(1)

    # Handle download-only mode
    if download_only:
        console.print("[bold]Downloading model(s)...[/bold]")
        for model_name in model:
            console.print(f"  Downloading [cyan]{model_name}[/cyan]...")
            try:
                from faster_whisper import WhisperModel  # noqa: PLC0415

                _ = WhisperModel(
                    model_name,
                    device="cpu",  # Don't need GPU for download
                    download_root=str(cache_dir) if cache_dir else None,
                )
                console.print(f"  [green]✓[/green] Downloaded {model_name}")
            except Exception as e:
                err_console.print(f"  [red]✗[/red] Failed to download {model_name}: {e}")
                raise typer.Exit(1) from e
        console.print("[bold green]All models downloaded successfully![/bold green]")
        return

    # Create registry and register models
    registry = create_whisper_registry(default_model=default_model or model[0])

    for model_name in model:
        config = WhisperModelConfig(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            ttl_seconds=ttl,
            cache_dir=cache_dir,
            backend_type=resolved_backend,  # type: ignore[arg-type]
        )
        registry.register(config)

    # Preload models if requested
    if preload:
        console.print("[bold]Preloading model(s)...[/bold]")
        asyncio.run(registry.preload())

    # Build Wyoming URI
    wyoming_uri = f"tcp://{host}:{wyoming_port}"

    actual_backend = resolved_backend

    # Print startup info
    console.print()
    console.print("[bold green]Starting Whisper ASR Server[/bold green]")
    console.print()
    console.print("[dim]Configuration:[/dim]")
    console.print(f"  Backend: [cyan]{actual_backend}[/cyan]")
    console.print()
    console.print("[dim]Endpoints:[/dim]")
    console.print(f"  HTTP API: [cyan]http://{host}:{port}[/cyan]")
    if not no_wyoming:
        console.print(f"  Wyoming:  [cyan]{wyoming_uri}[/cyan]")
    console.print()
    console.print("[dim]Models:[/dim]")
    for m in model:
        is_default = m == registry.default_model
        suffix = " [yellow](default)[/yellow]" if is_default else ""
        console.print(f"  • {m} (ttl={ttl}s){suffix}")
    console.print()
    console.print("[dim]Usage with agent-cli:[/dim]")
    console.print(
        f"  [cyan]ag transcribe --asr-provider openai "
        f"--asr-openai-base-url http://localhost:{port}/v1[/cyan]",
    )
    if not no_wyoming:
        console.print(
            f"  [cyan]ag transcribe --asr-provider wyoming --asr-wyoming-ip {host} "
            f"--asr-wyoming-port {wyoming_port}[/cyan]",
        )
    console.print()

    # Create and run the app
    from agent_cli.server.whisper.api import create_app  # noqa: PLC0415

    fastapi_app = create_app(
        registry,
        enable_wyoming=not no_wyoming,
        wyoming_uri=wyoming_uri,
    )

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
    )


@app.command("transcription-proxy")
@requires_extras("server")
def transcription_proxy_cmd(
    host: Annotated[
        str,
        typer.Option("--host", help="Host to bind the server to"),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to bind the server to"),
    ] = 61337,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for development"),
    ] = False,
) -> None:
    """Run transcription proxy server.

    This server proxies transcription requests to configured ASR providers
    (Wyoming, OpenAI, or Gemini) based on your agent-cli configuration.

    It exposes:
    - /transcribe endpoint for audio transcription
    - /health endpoint for health checks

    This is the original server command functionality.

    Examples:
        # Run on default port
        agent-cli server transcription-proxy

        # Run on custom port
        agent-cli server transcription-proxy --port 8080

    """
    _check_server_deps()

    console.print(
        f"[bold green]Starting Agent CLI transcription proxy on {host}:{port}[/bold green]",
    )
    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "agent_cli.server.proxy.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command("tts")
@requires_extras("server", "tts")
def tts_cmd(  # noqa: PLR0915
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help="Model name(s) to load. Piper: 'en_US-lessac-medium'. Kokoro: 'kokoro' (auto-downloads)",
        ),
    ] = None,
    default_model: Annotated[
        str | None,
        typer.Option(
            "--default-model",
            help="Default model when not specified in request",
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device",
            "-d",
            help="Device: auto, cpu, cuda, mps (Piper is CPU-only, Kokoro supports GPU)",
        ),
    ] = "auto",
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Model cache directory",
        ),
    ] = None,
    ttl: Annotated[
        int,
        typer.Option(
            "--ttl",
            help="Seconds before unloading idle model",
        ),
    ] = 300,
    preload: Annotated[
        bool,
        typer.Option(
            "--preload",
            help="Load model(s) at startup and wait for completion",
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Host to bind the server to",
        ),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="HTTP API port",
        ),
    ] = 10201,
    wyoming_port: Annotated[
        int,
        typer.Option(
            "--wyoming-port",
            help="Wyoming protocol port",
        ),
    ] = 10200,
    no_wyoming: Annotated[
        bool,
        typer.Option(
            "--no-wyoming",
            help="Disable Wyoming server",
        ),
    ] = False,
    download_only: Annotated[
        bool,
        typer.Option(
            "--download-only",
            help="Download model(s) and exit without starting server",
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            "-l",
            help="Logging level: debug, info, warning, error",
        ),
    ] = "info",
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Backend: auto, piper, kokoro",
        ),
    ] = "auto",
) -> None:
    """Run TTS server with TTL-based model unloading.

    The server provides:
    - OpenAI-compatible /v1/audio/speech endpoint
    - Wyoming protocol for Home Assistant integration
    - Voice list at /v1/voices

    Models are loaded lazily on first request and unloaded after being
    idle for the TTL duration, freeing memory for other applications.

    **Piper backend** (CPU-friendly):
    Models use names like 'en_US-lessac-medium', 'en_GB-alan-medium'.
    See https://github.com/rhasspy/piper for available models.

    **Kokoro backend** (GPU-accelerated):
    Model and voices auto-download from HuggingFace on first use.
    Voices: af_heart, af_bella, am_adam, bf_emma, bm_george, etc.
    See https://huggingface.co/hexgrad/Kokoro-82M for all voices.

    Examples:
        # Run with Kokoro (auto-downloads model and voices)
        agent-cli server tts --backend kokoro

        # Run with default Piper model
        agent-cli server tts --backend piper

        # Run with specific Piper model and 10-minute TTL
        agent-cli server tts --model en_US-lessac-medium --ttl 600

        # Download Kokoro model and voices without starting server
        agent-cli server tts --backend kokoro --model af_bella --model am_adam --download-only

        # Download Piper model without starting server
        agent-cli server tts --backend piper --model en_US-lessac-medium --download-only

    """
    # Setup Rich logging for consistent output
    setup_rich_logging(log_level, console=console)

    valid_backends = ("auto", "piper", "kokoro")
    if backend not in valid_backends:
        err_console.print(
            f"[bold red]Error:[/bold red] --backend must be one of: {', '.join(valid_backends)}",
        )
        raise typer.Exit(1)

    # Resolve backend for auto mode
    resolved_backend = backend
    if backend == "auto":
        from agent_cli.server.tts.backends import (  # noqa: PLC0415
            detect_backend as detect_tts_backend,
        )

        resolved_backend = detect_tts_backend()
        logger.info("Selected %s backend (auto-detected)", resolved_backend)

    _check_tts_deps(resolved_backend)

    from agent_cli.server.tts.model_manager import TTSModelConfig  # noqa: PLC0415
    from agent_cli.server.tts.model_registry import create_tts_registry  # noqa: PLC0415

    # Default model based on backend (Kokoro auto-downloads from HuggingFace)
    if model is None:
        model = ["kokoro"] if resolved_backend == "kokoro" else ["en_US-lessac-medium"]

    # Validate default model against model list
    if default_model is not None and default_model not in model:
        err_console.print(
            f"[bold red]Error:[/bold red] --default-model '{default_model}' "
            f"is not in the model list: {model}",
        )
        raise typer.Exit(1)

    if download_only:
        _download_tts_models(resolved_backend, model, cache_dir)
        return

    # Create registry and register models
    registry = create_tts_registry(default_model=default_model or model[0])

    for model_name in model:
        config = TTSModelConfig(
            model_name=model_name,
            device=device,
            ttl_seconds=ttl,
            cache_dir=cache_dir,
            backend_type=resolved_backend,  # type: ignore[arg-type]
        )
        registry.register(config)

    # Preload models if requested
    if preload:
        console.print("[bold]Preloading model(s)...[/bold]")
        asyncio.run(registry.preload())

    # Build Wyoming URI
    wyoming_uri = f"tcp://{host}:{wyoming_port}"

    # Print startup info
    console.print()
    console.print("[bold green]Starting TTS Server[/bold green]")
    console.print()
    console.print("[dim]Configuration:[/dim]")
    console.print(f"  Backend: [cyan]{resolved_backend}[/cyan]")
    console.print()
    console.print("[dim]Endpoints:[/dim]")
    console.print(f"  HTTP API: [cyan]http://{host}:{port}[/cyan]")
    if not no_wyoming:
        console.print(f"  Wyoming:  [cyan]{wyoming_uri}[/cyan]")
    console.print()
    console.print("[dim]Models:[/dim]")
    for m in model:
        is_default = m == registry.default_model
        suffix = " [yellow](default)[/yellow]" if is_default else ""
        console.print(f"  • {m} (ttl={ttl}s){suffix}")
    console.print()
    console.print("[dim]Usage with OpenAI client:[/dim]")
    console.print(
        "  [cyan]from openai import OpenAI[/cyan]",
    )
    console.print(
        f'  [cyan]client = OpenAI(base_url="http://localhost:{port}/v1", api_key="x")[/cyan]',
    )
    if resolved_backend == "kokoro":
        console.print(
            '  [cyan]response = client.audio.speech.create(model="tts-1", voice="af_heart", '
            'input="Hello")[/cyan]',
        )
    else:
        console.print(
            '  [cyan]response = client.audio.speech.create(model="tts-1", voice="alloy", '
            'input="Hello")[/cyan]',
        )
    console.print()

    # Create and run the app
    from agent_cli.server.tts.api import create_app  # noqa: PLC0415

    fastapi_app = create_app(
        registry,
        enable_wyoming=not no_wyoming,
        wyoming_uri=wyoming_uri,
    )

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level=log_level.lower(),
    )
