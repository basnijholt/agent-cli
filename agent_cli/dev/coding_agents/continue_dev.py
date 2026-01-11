"""Continue Dev CLI coding agent adapter."""

from __future__ import annotations

from .base import CodingAgent, _get_parent_process_names


class ContinueDev(CodingAgent):
    """Continue Dev - AI code assistant."""

    name = "continue"
    command = "cn"
    alt_commands = ("continue",)
    install_url = "https://continue.dev"

    def detect(self) -> bool:
        """Detect if running inside Continue Dev.

        Custom detection needed because command is 'cn' but process may be 'continue'.
        """
        parent_names = _get_parent_process_names()
        return any("continue" in name or name == "cn" for name in parent_names)
