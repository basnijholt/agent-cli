"""Utility functions for Wyoming protocol interactions to eliminate code duplication."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from wyoming.client import AsyncClient

from agent_cli.utils import print_error_message

if TYPE_CHECKING:
    import logging
    from collections.abc import AsyncGenerator, Coroutine


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
    uri = f"tcp://{server_ip}:{server_port}"
    logger.info("Connecting to Wyoming %s server at %s", server_type, uri)

    try:
        async with AsyncClient.from_uri(uri) as client:
            logger.info("%s connection established", server_type)
            yield client
    except ConnectionRefusedError:
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


async def manage_send_receive_tasks(
    send_task_coro: Coroutine,
    receive_task_coro: Coroutine,
    *,
    return_when: str = asyncio.ALL_COMPLETED,
) -> tuple[asyncio.Task, asyncio.Task]:
    """Manage send and receive tasks with proper cancellation.

    Args:
        send_task_coro: Send task coroutine
        receive_task_coro: Receive task coroutine
        return_when: When to return (e.g., asyncio.ALL_COMPLETED)

    Returns:
        Tuple of (send_task, receive_task) - both completed or cancelled

    """
    send_task = asyncio.create_task(send_task_coro)
    recv_task = asyncio.create_task(receive_task_coro)

    done, pending = await asyncio.wait(
        [send_task, recv_task],
        return_when=return_when,
    )

    # Cancel any pending tasks
    for task in pending:
        task.cancel()

    return send_task, recv_task
