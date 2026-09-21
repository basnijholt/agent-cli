"""Tests for macOS hotkey shell script behavior."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOGGLE_TRANSCRIPTION = ROOT / "scripts" / "macos-hotkeys" / "toggle-transcription.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_toggle_script(
    tmp_path: Path,
    agent_cli_body: str,
    *,
    expected_notifications: int = 2,
) -> tuple[list[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    notification_log = tmp_path / "notifications.log"

    _write_executable(
        bin_dir / "agent-cli",
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "{command_log}"
{agent_cli_body}
""",
    )
    _write_executable(
        bin_dir / "terminal-notifier",
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{notification_log}"
""",
    )

    env = {
        **os.environ,
        "AGENT_CLI": str(bin_dir / "agent-cli"),
        "NOTIFIER": str(bin_dir / "terminal-notifier"),
        "HOME": str(tmp_path),
    }
    subprocess.run([str(TOGGLE_TRANSCRIPTION)], check=True, env=env)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        command_count = (
            len(command_log.read_text(encoding="utf-8").splitlines()) if command_log.exists() else 0
        )
        notification_count = (
            len(notification_log.read_text(encoding="utf-8").splitlines())
            if notification_log.exists()
            else 0
        )
        if command_count >= 2 and notification_count >= expected_notifications:
            break
        time.sleep(0.01)

    commands = command_log.read_text(encoding="utf-8").splitlines() if command_log.exists() else []
    notifications = (
        notification_log.read_text(encoding="utf-8").splitlines()
        if notification_log.exists()
        else []
    )
    return commands, notifications


def test_macos_transcription_hotkey_stops_using_process_status_json(tmp_path: Path) -> None:
    commands, notifications = _run_toggle_script(
        tmp_path,
        """
if [[ "$*" == "transcribe --status --json" ]]; then
    printf '{"action":"status","process":"transcribe","running":true,"status":"running","pid":123,"stale_cleaned":false}\\n'
    exit 0
fi
if [[ "$*" == "transcribe --stop --quiet --wait-for-start"* ]]; then
    exit 0
fi
printf 'unexpected command: %s\\n' "$*" >&2
exit 2
""",
    )

    assert commands[0] == "transcribe --status --json"
    assert commands[1].startswith("transcribe --stop --quiet --wait-for-start")
    assert not any("--toggle" in command for command in commands)
    assert any("Stopped" in notification for notification in notifications)


def test_macos_transcription_hotkey_starts_from_process_status_json(tmp_path: Path) -> None:
    commands, notifications = _run_toggle_script(
        tmp_path,
        """
if [[ "$*" == "transcribe --status --json" ]]; then
    printf '{"action":"status","process":"transcribe","running":false,"status":"stopped","pid":null,"stale_cleaned":false}\\n'
    exit 0
fi
if [[ "$*" == "transcribe --start --llm --quiet"* ]]; then
    printf 'hello from transcript\\n'
    exit 0
fi
printf 'unexpected command: %s\\n' "$*" >&2
exit 2
""",
        expected_notifications=3,
    )

    assert commands[0] == "transcribe --status --json"
    assert commands[1].startswith("transcribe --start --llm --quiet")
    assert not any("--toggle" in command for command in commands)
    assert any("Recording" in notification for notification in notifications)
    assert any("hello from transcript" in notification for notification in notifications)
