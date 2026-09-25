"""Exercise the shipped cleanup script without touching the user's launchd services."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "macos" / "uninstall-macos-app.sh"
pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS PlistBuddy")


@pytest.mark.parametrize(
    ("owner", "loaded", "bootout_status", "removed", "expected_status"),
    [
        ("this-app", True, 0, True, 0),
        ("this-app", False, 0, True, 0),
        ("this-app", True, 5, False, 5),
        ("standalone", True, 0, False, 0),
        ("other-app", True, 0, False, 0),
        ("missing", True, 0, False, 0),
        ("malformed", True, 0, False, 0),
    ],
)
def test_uninstall_preserves_independent_services(
    tmp_path: Path,
    owner: str,
    loaded: bool,
    bootout_status: int,
    removed: bool,
    expected_status: int,
) -> None:
    """Only this bundle's service is removed, and only after a successful shutdown.

    PlistBuddy and filesystem operations are real. Only launchctl is substituted:
    running it against the shared label could stop the developer's live daemon.
    """
    resources = tmp_path / "Applications with spaces" / "AgentCLI.app/Contents/Resources"
    resources.mkdir(parents=True)
    home = tmp_path / "home"
    plist = home / "Library/LaunchAgents/com.agent_cli.whisper.plist"
    plist.parent.mkdir(parents=True)
    unrelated = home / "Library/LaunchAgents/com.example.other.plist"
    unrelated.write_text("unrelated")
    if owner != "missing":
        if owner == "malformed":
            plist.write_text("invalid plist")
        else:
            environment = {}
            if owner == "this-app":
                environment["AGENTCLI_BUNDLED_UV"] = str(resources / "bin/uv")
            elif owner == "other-app":
                environment["AGENTCLI_BUNDLED_UV"] = (
                    "/Applications/Other.app/Contents/Resources/bin/uv"
                )
            plist.write_bytes(
                plistlib.dumps(
                    {
                        "Label": "com.agent_cli.whisper",
                        "EnvironmentVariables": environment,
                        "ProgramArguments": ["/bin/sleep", "3600"],
                    }
                )
            )
    before = plist.read_bytes() if plist.exists() else None
    calls = tmp_path / "launchctl-calls"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'case "$1" in\n'
        '  print) exit "$PRINT_STATUS" ;;\n'
        '  bootout) exit "$BOOTOUT_STATUS" ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    launchctl.chmod(0o755)
    helper = resources / "uninstall.sh"
    helper.write_text(SCRIPT.read_text().replace("/bin/launchctl", f'"{launchctl}"'))
    helper.chmod(0o755)
    result = subprocess.run(
        [str(helper)],
        cwd=tmp_path,
        env={
            **os.environ,
            "HOME": str(home),
            "CALL_LOG": str(calls),
            "PRINT_STATUS": "0" if loaded else "113",
            "BOOTOUT_STATUS": str(bootout_status),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_status, result.stderr
    assert unrelated.read_text() == "unrelated"
    if removed or owner == "missing":
        assert not plist.exists()
    else:
        assert plist.read_bytes() == before
    service = f"gui/{os.getuid()}/com.agent_cli.whisper"
    expected_calls = []
    if owner == "this-app":
        expected_calls = [f"print {service}"]
        if loaded:
            expected_calls.append(f"bootout {service}")
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected_calls
