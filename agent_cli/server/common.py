"""Common utilities for FastAPI server modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.logging import RichHandler

from agent_cli import constants

if TYPE_CHECKING:
    import wave

    from fastapi import Request

logger = logging.getLogger(__name__)


def setup_rich_logging(log_level: str = "info", *, console: Console | None = None) -> None:
    """Configure logging to use Rich for consistent, pretty output.

    This configures:
    - All Python loggers to use RichHandler
    - Uvicorn's loggers to use the same format

    Args:
        log_level: Logging level (debug, info, warning, error).
        console: Optional Rich console to use (creates new one if not provided).

    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    rich_console = console or Console()

    # Create Rich handler with clean format
    handler = RichHandler(
        console=rich_console,
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
