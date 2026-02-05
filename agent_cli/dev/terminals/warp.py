"""Warp terminal adapter.

Uses Warp's URI scheme and Launch Configurations for reliable automation.
Evidence: https://docs.warp.dev/terminal/more-features/uri-scheme
Evidence: https://docs.warp.dev/terminal/sessions/launch-configurations
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from .base import Terminal, _get_term_program


def _get_warp_launch_config_dir() -> Path:
    """Get the Warp launch configurations directory."""
    return Path.home() / ".warp" / "launch_configurations"


class Warp(Terminal):
    """Warp - Modern, Rust-based terminal with AI features."""

    name = "warp"

    def detect(self) -> bool:
        """Detect if running inside Warp."""
        term_program = _get_term_program()
        return term_program is not None and "warp" in term_program.lower()

    def is_available(self) -> bool:
        """Check if Warp is available (macOS only for now)."""
        if sys.platform != "darwin":
            return False
        return Path("/Applications/Warp.app").exists()

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in Warp.

        Uses URI scheme for simple path-only tabs, or Launch Configurations
        when a command needs to be executed.

        Evidence:
            URI scheme: https://docs.warp.dev/terminal/more-features/uri-scheme
            Launch configs: https://docs.warp.dev/terminal/sessions/launch-configurations
        """
        if not self.is_available():
            return False

        # Simple case: no command, just open path via URI scheme
        # Note: tab_name is ignored here - URI scheme doesn't support tab naming
        if command is None:
            try:
                subprocess.run(
                    ["open", f"warp://action/new_tab?path={path}"],  # noqa: S607
                    check=True,
                    capture_output=True,
                )
                return True
            except subprocess.CalledProcessError:
                return False

        # Complex case: need to run a command - use Launch Configuration
        return self._open_with_launch_config(path, command, tab_name)

    def _open_with_launch_config(
        self,
        path: Path,
        command: str,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab using a temporary Launch Configuration.

        Creates a YAML config file, opens it via URI scheme, then cleans up.
        """
        config_dir = _get_warp_launch_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create unique config file name
        config_name = f"agent-cli-{uuid.uuid4().hex[:8]}"
        config_file = config_dir / f"{config_name}.yaml"

        # Build the YAML config
        # Quote values that may contain special YAML characters (: # etc.)
        title = tab_name or "agent-cli"
        # Escape single quotes by doubling them, then wrap in single quotes
        escaped_command = command.replace("'", "''")
        yaml_content = f"""---
name: {config_name}
windows:
  - tabs:
      - title: '{title}'
        layout:
          cwd: '{path.as_posix()}'
          commands:
            - exec: '{escaped_command}'
"""

        try:
            # Write config file
            config_file.write_text(yaml_content)

            # Open via URI scheme
            result = subprocess.run(
                ["open", f"warp://launch/{config_file}"],  # noqa: S607
                check=True,
                capture_output=True,
            )

            # Clean up after a delay (give Warp time to read the file)
            # We use a background process to delete after 2 seconds
            subprocess.Popen(
                ["sh", "-c", f'sleep 2 && rm -f "{config_file}"'],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return result.returncode == 0
        except subprocess.CalledProcessError:
            # Clean up on failure
            config_file.unlink(missing_ok=True)
            return False
        except Exception:
            config_file.unlink(missing_ok=True)
            return False
