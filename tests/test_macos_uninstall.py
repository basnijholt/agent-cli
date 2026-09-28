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
    (
        "owner",
        "loaded_owner",
        "print_status",
        "bootout_status",
        "shutdown_polls",
        "shutdown_status",
        "removed",
        "expected_status",
    ),
    [
        ("this-app", "this-app", 0, 0, 0, 113, True, 0),
        ("this-app", "absent", 113, 0, 0, 113, True, 0),
        ("this-app", "this-app", 0, 5, 0, 113, False, 5),
        ("standalone", "standalone", 0, 0, 0, 113, False, 0),
        ("other-app", "other-app", 0, 0, 0, 113, False, 0),
        ("missing", "this-app", 0, 0, 0, 113, False, 0),
        ("malformed", "this-app", 0, 0, 0, 113, False, 0),
        ("this-app", "standalone", 0, 0, 0, 113, False, 1),
        ("this-app", "other-app", 0, 0, 0, 113, False, 1),
        ("this-app", "malformed", 0, 0, 0, 113, False, 1),
        ("this-app", "inherited-only", 0, 0, 0, 113, False, 1),
        ("this-app", "this-app", 5, 0, 0, 113, False, 5),
        ("this-app", "this-app", 0, 0, 2, 113, True, 0),
        ("this-app", "this-app", 0, 0, 99, 113, False, 1),
        ("this-app", "this-app", 0, 0, 0, 5, False, 5),
    ],
)
def test_uninstall_preserves_independent_services(
    tmp_path: Path,
    owner: str,
    loaded_owner: str,
    print_status: int,
    bootout_status: int,
    shutdown_polls: int,
    shutdown_status: int,
    removed: bool,
    expected_status: int,
) -> None:
    """Only this bundle's service is removed, and only after a successful shutdown.

    PlistBuddy and filesystem operations are real. Launchctl and its polling delay are substituted:
    running it against the shared label could stop the developer's live daemon.
    launchctl(1) documents print output as unstable; unknown output must preserve
    the service. The current tab-indented fields were verified on macOS, and
    `launchctl error 113` identifies the service-not-found status.
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
    loaded_uv = {
        "this-app": str(resources / "bin/uv"),
        "inherited-only": str(resources / "bin/uv"),
        "other-app": "/Applications/Other.app/Contents/Resources/bin/uv",
    }.get(loaded_owner, "/usr/local/bin/uv")
    output = tmp_path / "launchctl-output"
    output.write_text(
        f"gui/{os.getuid()}/com.agent_cli.whisper = {{\n"
        f"\tprogram = {loaded_uv}\n"
        "\tinherited environment = {\n"
        f"\t\tAGENTCLI_BUNDLED_UV => {resources / 'bin/uv'}\n"
        "\t}\n"
        "\tenvironment = {\n"
        + (
            f"\t\tAGENTCLI_BUNDLED_UV => {loaded_uv}\n"
            if loaded_owner not in {"standalone", "inherited-only"}
            else ""
        )
        + "\t}\n}\n"
    )
    if loaded_owner == "malformed":
        output.write_text("unexpected output")
    calls = tmp_path / "launchctl-calls"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$CALL_LOG"\n'
        'case "$1" in\n'
        "  print)\n"
        '    if [ -f "$STOP_STATE" ]; then\n'
        '      count=$(/bin/cat "$STOP_STATE")\n'
        '      printf "%s" "$((count + 1))" > "$STOP_STATE"\n'
        '      [ "$count" -lt "$SHUTDOWN_POLLS" ] && exit 0\n'
        '      exit "$SHUTDOWN_STATUS"\n'
        "    fi\n"
        '    /bin/cat "$PRINT_OUTPUT"; exit "$PRINT_STATUS" ;;\n'
        "  bootout)\n"
        '    [ "$BOOTOUT_STATUS" -eq 0 ] && printf 0 > "$STOP_STATE"\n'
        '    exit "$BOOTOUT_STATUS" ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    launchctl.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    helper = resources / "uninstall.sh"
    helper.write_text(
        SCRIPT.read_text()
        .replace("/bin/launchctl", f'"{launchctl}"')
        .replace("/bin/sleep", f'"{sleep}"')
    )
    helper.chmod(0o755)
    result = subprocess.run(
        [str(helper)],
        cwd=tmp_path,
        env={
            **os.environ,
            "HOME": str(home),
            "CALL_LOG": str(calls),
            "PRINT_STATUS": str(print_status),
            "PRINT_OUTPUT": str(output),
            "BOOTOUT_STATUS": str(bootout_status),
            "STOP_STATE": str(tmp_path / "stopping"),
            "SHUTDOWN_POLLS": str(shutdown_polls),
            "SHUTDOWN_STATUS": str(shutdown_status),
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
        if print_status == 0 and loaded_owner == "this-app":
            expected_calls.append(f"bootout {service}")
            if bootout_status == 0:
                expected_calls += [f"print {service}"] * (
                    31 if shutdown_polls == 99 else shutdown_polls + 1
                )
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected_calls
