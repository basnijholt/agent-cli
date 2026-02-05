"""Wakeword server - Wyoming protocol only."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_cli.server.wakeword.model_registry import WakewordModelRegistry

logger = logging.getLogger(__name__)


async def run_server(
    registry: WakewordModelRegistry,
    wyoming_uri: str = "tcp://0.0.0.0:10400",
) -> None:
    """Run the wakeword server (Wyoming protocol only).

    Args:
        registry: Model registry for wakeword detection.
        wyoming_uri: URI for Wyoming server.

    """
    from agent_cli.server.wakeword.wyoming_handler import (  # noqa: PLC0415
        start_wyoming_server,
    )

    # Start the registry (TTL watchers)
    await registry.start()

    try:
        # Run Wyoming server (blocks until shutdown)
        await start_wyoming_server(registry, wyoming_uri)
    finally:
        # Stop the registry
        await registry.stop()
