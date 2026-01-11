"""Continue Dev CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent


class ContinueDev(CodingAgent):
    """Continue Dev - AI code assistant."""

    name = "continue"
    command = "cn"
    install_url = "https://continue.dev"
    # Detection via cmdline extraction (cn runs as 'node' but cmdline contains '/path/to/cn')
    detect_process_name = "cn"
