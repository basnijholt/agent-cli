"""Utility functions for Wyoming protocol interactions to eliminate code duplication."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from agent_cli.core.utils import print_error_message

if TYPE_CHECKING:
    import logging
    from collections.abc import AsyncGenerator

    from wyoming.client import AsyncClient


@asynccontextmanager
async def wyoming_client_context(
    server_ip: str,
    server_port: int,
    server_type: str,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> AsyncGenerator[AsyncClient, None]:
    """Context manager for Wyoming client connections with unified error handling.

    Args:
        server_ip: Wyoming server IP
        server_port: Wyoming server port
        server_type: Type of server (e.g., "ASR", "TTS", "wake word")
        logger: Logger instance
        quiet: If True, suppress console error messages

    Yields:
        Connected Wyoming client

    Raises:
        ConnectionRefusedError: If connection fails
        Exception: For other connection errors

    """
    from wyoming.client import AsyncClient  # noqa: PLC0415

    uri = f"tcp://{server_ip}:{server_port}"
    logger.info("Connecting to Wyoming %s server at %s", server_type, uri)

    try:
        async with AsyncClient.from_uri(uri) as client:
            logger.info("%s connection established", server_type)
            yield client
    except ConnectionRefusedError:
        logger.exception("%s connection refused.", server_type)
        if not quiet:
            print_error_message(
                f"{server_type} connection refused.",
                f"Is the Wyoming {server_type.lower()} server running at {uri}?",
            )
        raise
    except Exception as e:
        logger.exception("An error occurred during %s connection", server_type.lower())
        if not quiet:
            print_error_message(f"{server_type} error: {e}")
        raise
