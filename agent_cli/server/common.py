"""Common utilities for FastAPI server modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


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
