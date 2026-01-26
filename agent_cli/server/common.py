"""Common utilities for FastAPI server modules."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

from rich.logging import RichHandler

from agent_cli import constants
from agent_cli.core.utils import console

if TYPE_CHECKING:
    import wave
    from collections.abc import AsyncIterator, Callable, Coroutine
    from contextlib import AbstractAsyncContextManager

    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


class RegistryProtocol(Protocol):
    """Protocol for model registries."""

    async def start(self) -> None:
        """Start the registry."""
        ...

    async def stop(self) -> None:
        """Stop the registry."""
        ...

    async def preload(self) -> None:
        """Preload models."""
        ...


def create_lifespan(
    registry: RegistryProtocol,
    *,
    wyoming_handler_module: str,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:10300",
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create a lifespan context manager for a server.

    Args:
        registry: The model registry to manage.
        wyoming_handler_module: Module path containing start_wyoming_server function.
        enable_wyoming: Whether to start Wyoming server.
        wyoming_uri: URI for Wyoming server.

    Returns:
        A lifespan context manager function for FastAPI.

    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle."""
        wyoming_task: asyncio.Task[None] | None = None

        # Start the registry
        await registry.start()

        # Start Wyoming server if enabled
        if enable_wyoming:
            try:
                module = importlib.import_module(wyoming_handler_module)
                start_wyoming_server: Callable[
                    [Any, str],
                    Coroutine[Any, Any, None],
                ] = module.start_wyoming_server

                wyoming_task = asyncio.create_task(
                    start_wyoming_server(registry, wyoming_uri),
                )
            except ImportError:
                logger.warning("Wyoming not available, skipping Wyoming server")
            except Exception:
                logger.exception("Failed to start Wyoming server")

        yield

        # Stop Wyoming server
        if wyoming_task is not None:
            wyoming_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wyoming_task

        # Stop the registry
        await registry.stop()

    return lifespan


def configure_app(app: FastAPI) -> None:
    """Configure a FastAPI app with common middleware.

    Adds:
    - CORS middleware allowing all origins
    - Request logging middleware

    Args:
        app: The FastAPI application to configure.

    """
    from fastapi.middleware.cors import CORSMiddleware  # noqa: PLC0415

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Any, call_next: Any) -> Any:
        """Log basic request information."""
        return await log_requests_middleware(request, call_next)


def setup_rich_logging(log_level: str = "info") -> None:
    """Configure logging to use Rich for consistent, pretty output.

    This configures:
    - All Python loggers to use RichHandler
    - Uvicorn's loggers to use the same format

    Args:
        log_level: Logging level (debug, info, warning, error).
        console: Optional Rich console to use (creates new one if not provided).

    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create Rich handler with clean format
    handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,  # Don't show file:line - too verbose
        rich_tracebacks=True,
        markup=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Configure root logger
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Configure uvicorn loggers to use same handler
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.setLevel(level)
        uvicorn_logger.propagate = False


def setup_wav_file(
    wav_file: wave.Wave_write,
    *,
    rate: int | None = None,
    channels: int | None = None,
    sample_width: int | None = None,
) -> None:
    """Configure a WAV file with standard audio parameters.

    Args:
        wav_file: The WAV file writer to configure.
        rate: Sample rate in Hz (default: constants.AUDIO_RATE).
        channels: Number of channels (default: constants.AUDIO_CHANNELS).
        sample_width: Sample width in bytes (default: constants.AUDIO_FORMAT_WIDTH).

    """
    wav_file.setnchannels(channels or constants.AUDIO_CHANNELS)
    wav_file.setsampwidth(sample_width or constants.AUDIO_FORMAT_WIDTH)
    wav_file.setframerate(rate or constants.AUDIO_RATE)


async def log_requests_middleware(
    request: Request,
    call_next: Any,
) -> Any:
    """Log basic request information.

    This middleware logs incoming requests and warns on errors.
    Use with FastAPI's @app.middleware("http") decorator.

    Args:
        request: The incoming request.
        call_next: The next middleware/handler in the chain.

    Returns:
        The response from the next handler.

    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info("%s %s from %s", request.method, request.url.path, client_ip)

    response = await call_next(request)

    if response.status_code >= 400:  # noqa: PLR2004
        logger.warning(
            "Request failed: %s %s → %d",
            request.method,
            request.url.path,
            response.status_code,
        )

    return response
