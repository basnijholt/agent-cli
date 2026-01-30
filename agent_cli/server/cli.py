"""CLI commands for the server module."""

from __future__ import annotations

import asyncio
import logging
from importlib.util import find_spec
from pathlib import Path  # noqa: TC003 - Typer needs this at runtime
from typing import Annotated

import typer

from agent_cli import opts
from agent_cli.cli import app as main_app
from agent_cli.core.deps import requires_extras
from agent_cli.core.process import set_process_title
from agent_cli.core.utils import console, err_console
from agent_cli.server.common import setup_rich_logging

logger = logging.getLogger(__name__)

# Check for optional dependencies at call time (not module load time)
# This is important because auto-install may install packages after the module is loaded


def _has(package: str) -> bool:
    return find_spec(package) is not None


app = typer.Typer(
    name="server",
    help="""Run local ASR/TTS servers with OpenAI-compatible APIs.

**Available servers:**

- `whisper` - Local speech-to-text using Whisper models (faster-whisper or MLX)
- `tts` - Local text-to-speech using Piper (CPU) or Kokoro (GPU)
- `transcribe-proxy` - Proxy to external ASR providers (OpenAI, Gemini, Wyoming)

**Common workflows:**

```bash
# Run local Whisper server (lazy loads large-v3 by default)
agent-cli server whisper

# Run local TTS with Kokoro backend (GPU-accelerated)
agent-cli server tts --backend kokoro

# Run transcription proxy using your configured ASR provider
agent-cli server transcribe-proxy
```

All servers support Home Assistant via Wyoming protocol and can be used as
drop-in replacements for OpenAI's audio APIs.
""",
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
    if not _has("uvicorn") or not _has("fastapi"):
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
        if not _has("kokoro"):
            err_console.print(
                "[bold red]Error:[/bold red] Kokoro backend requires kokoro. "
                "Run: [cyan]pip install agent-cli\\[tts-kokoro][/cyan] "
                "or [cyan]uv sync --extra tts-kokoro[/cyan]",
            )
            raise typer.Exit(1)
        return

    if backend == "piper":
        if not _has("piper"):
            err_console.print(
                "[bold red]Error:[/bold red] Piper backend requires piper-tts. "
                "Run: [cyan]pip install agent-cli\\[tts][/cyan] "
                "or [cyan]uv sync --extra tts[/cyan]",
            )
            raise typer.Exit(1)
        return

    # For auto, check if either is available
    if not _has("piper") and not _has("kokoro"):
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
        if not _has("faster_whisper"):
            err_console.print(
                "[bold red]Error:[/bold red] faster-whisper is required for --download-only. "
                "Run: [cyan]pip install agent-cli\\[whisper][/cyan] "
                "or [cyan]uv sync --extra whisper[/cyan]",
            )
            raise typer.Exit(1)
        return

    if backend == "mlx":
        if not _has("mlx_whisper"):
            err_console.print(
                "[bold red]Error:[/bold red] MLX Whisper backend requires mlx-whisper. "
                "Run: [cyan]pip install mlx-whisper[/cyan]",
            )
            raise typer.Exit(1)
        return

    if not _has("faster_whisper"):
        err_console.print(
            "[bold red]Error:[/bold red] Whisper dependencies not installed. "
            "Run: [cyan]pip install agent-cli\\[whisper][/cyan] "
            "or [cyan]uv sync --extra whisper[/cyan]",
        )
        raise typer.Exit(1)


@app.command("whisper")
@requires_extras("server", "faster-whisper|mlx-whisper")
def whisper_cmd(  # noqa: PLR0912, PLR0915
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Whisper model(s) to load. Common models: `tiny`, `base`, `small`, "
                "`medium`, `large-v3`, `distil-large-v3`. Can specify multiple for "
                "different accuracy/speed tradeoffs. Default: `large-v3`"
            ),
        ),
    ] = None,
    default_model: Annotated[
        str | None,
        typer.Option(
            "--default-model",
            help=("Model to use when client doesn't specify one. Must be in the `--model` list"),
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device",
            "-d",
            help=(
                "Compute device: `auto` (detect GPU), `cuda`, `cuda:0`, `cpu`. "
                "MLX backend always uses Apple Silicon"
            ),
        ),
    ] = "auto",
    compute_type: Annotated[
        str,
        typer.Option(
            "--compute-type",
            help=(
                "Precision for faster-whisper: `auto`, `float16`, `int8`, `int8_float16`. "
                "Lower precision = faster + less VRAM"
            ),
        ),
    ] = "auto",
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Custom directory for downloaded models (default: HuggingFace cache)",
        ),
    ] = None,
    ttl: Annotated[
        int,
        typer.Option(
            "--ttl",
            help=(
                "Seconds of inactivity before unloading model from memory. "
                "Set to 0 to keep loaded indefinitely"
            ),
        ),
    ] = 300,
    preload: Annotated[
        bool,
        typer.Option(
            "--preload",
            help=(
                "Load model(s) immediately at startup instead of on first request. "
                "Useful for reducing first-request latency"
            ),
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Network interface to bind. Use `0.0.0.0` for all interfaces",
        ),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port for OpenAI-compatible HTTP API (`/v1/audio/transcriptions`)",
        ),
    ] = 10301,
    wyoming_port: Annotated[
        int,
        typer.Option(
            "--wyoming-port",
            help="Port for Wyoming protocol (Home Assistant integration)",
        ),
    ] = 10300,
    no_wyoming: Annotated[
        bool,
        typer.Option(
            "--no-wyoming",
            help="Disable Wyoming protocol server (only run HTTP API)",
        ),
    ] = False,
    download_only: Annotated[
        bool,
        typer.Option(
            "--download-only",
            help="Download model(s) to cache and exit. Useful for Docker builds",
        ),
    ] = False,
    log_level: opts.LogLevel = opts.SERVER_LOG_LEVEL,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help=(
                "Inference backend: `auto` (faster-whisper on CUDA/CPU, MLX on Apple Silicon), "
                "`faster-whisper`, `mlx`"
            ),
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

    **Examples:**

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
    setup_rich_logging(log_level)

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
    console.print(f"  Log level: [cyan]{log_level}[/cyan]")
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


@app.command("transcribe-proxy")
@requires_extras("server", "wyoming", "llm")
def transcribe_proxy_cmd(
    host: Annotated[
        str,
        typer.Option("--host", help="Network interface to bind. Use `0.0.0.0` for all interfaces"),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port for the HTTP API"),
    ] = 61337,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Auto-reload on code changes (development only)"),
    ] = False,
    log_level: opts.LogLevel = opts.SERVER_LOG_LEVEL,
) -> None:
    r"""Run transcription proxy that forwards to your configured ASR provider.

    Unlike `server whisper` which runs a local Whisper model, this proxy
    forwards audio to external ASR providers configured in your agent-cli
    config file or environment variables.

    **Supported ASR providers:** `wyoming`, `openai`, `gemini`
    **Supported LLM providers for cleanup:** `ollama`, `openai`, `gemini`

    The server exposes:

    - `POST /transcribe` - Accepts audio files, returns `{raw_transcript, cleaned_transcript}`
    - `GET /health` - Health check endpoint

    **When to use this vs `server whisper`:**

    - Use `transcribe-proxy` when you want to use cloud ASR (OpenAI/Gemini)
      or connect to a remote Wyoming server
    - Use `server whisper` when you want to run a local Whisper model

    Configuration is read from `~/.config/agent-cli/config.yaml` or env vars
    like `ASR_PROVIDER`, `LLM_PROVIDER`, `OPENAI_API_KEY`, etc.

    **Examples:**

        # Run with providers from config file
        agent-cli server transcribe-proxy

        # Run with OpenAI ASR via env vars
        ASR_PROVIDER=openai OPENAI_API_KEY=sk-... agent-cli server transcribe-proxy

        # Test with curl
        curl -X POST http://localhost:61337/transcribe \\
          -F "audio=@recording.wav" -F "cleanup=true"
    """
    _check_server_deps()
    setup_rich_logging(log_level)

    console.print(
        f"[bold green]Starting Agent CLI transcription proxy on {host}:{port}[/bold green]",
    )
    console.print(f"[dim]Log level: {log_level}[/dim]")
    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "agent_cli.server.proxy.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level.lower(),
    )


@app.command("tts")
@requires_extras("server", "piper|kokoro")
def tts_cmd(  # noqa: PLR0915
    model: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            "-m",
            help=(
                "Model/voice(s) to load. Piper: `en_US-lessac-medium`, `en_GB-alan-medium`. "
                "Kokoro: `af_heart`, `af_bella`, `am_adam`. "
                "Auto-downloads on first use"
            ),
        ),
    ] = None,
    default_model: Annotated[
        str | None,
        typer.Option(
            "--default-model",
            help=("Voice to use when client doesn't specify one. Must be in the `--model` list"),
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option(
            "--device",
            "-d",
            help=(
                "Compute device: `auto`, `cpu`, `cuda`, `mps`. "
                "Piper is CPU-only; Kokoro supports GPU acceleration"
            ),
        ),
    ] = "auto",
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help="Custom directory for downloaded models (default: ~/.cache/agent-cli/tts/)",
        ),
    ] = None,
    ttl: Annotated[
        int,
        typer.Option(
            "--ttl",
            help=(
                "Seconds of inactivity before unloading model from memory. "
                "Set to 0 to keep loaded indefinitely"
            ),
        ),
    ] = 300,
    preload: Annotated[
        bool,
        typer.Option(
            "--preload",
            help=(
                "Load model(s) immediately at startup instead of on first request. "
                "Useful for reducing first-request latency"
            ),
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Network interface to bind. Use `0.0.0.0` for all interfaces",
        ),
    ] = "0.0.0.0",  # noqa: S104
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port for OpenAI-compatible HTTP API (`/v1/audio/speech`)",
        ),
    ] = 10201,
    wyoming_port: Annotated[
        int,
        typer.Option(
            "--wyoming-port",
            help="Port for Wyoming protocol (Home Assistant integration)",
        ),
    ] = 10200,
    no_wyoming: Annotated[
        bool,
        typer.Option(
            "--no-wyoming",
            help="Disable Wyoming protocol server (only run HTTP API)",
        ),
    ] = False,
    download_only: Annotated[
        bool,
        typer.Option(
            "--download-only",
            help="Download model(s)/voice(s) to cache and exit. Useful for Docker builds",
        ),
    ] = False,
    log_level: opts.LogLevel = opts.SERVER_LOG_LEVEL,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help=(
                "TTS engine: `auto` (prefer Kokoro if available), "
                "`piper` (CPU, many languages), `kokoro` (GPU, high quality)"
            ),
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

    **Examples:**

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
    setup_rich_logging(log_level)

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
    console.print(f"  Log level: [cyan]{log_level}[/cyan]")
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
