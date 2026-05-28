#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-cli-macos-e2e.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

INSTALL_DIR="$TMP_DIR/Applications"
APP="$INSTALL_DIR/AgentCLI.app"
DMG="$ROOT_DIR/dist/macos/AgentCLI.dmg"
FAKE_BIN="$TMP_DIR/fake-bin"
FAKE_UV="$FAKE_BIN/uv"
COMMAND_LOG="$TMP_DIR/commands.log"

mkdir -p "$FAKE_BIN"
cat >"$FAKE_UV" <<'FAKE_UV'
#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${AGENTCLI_TEST_COMMAND_LOG:-}" ]]; then
    printf 'uv' >>"$AGENTCLI_TEST_COMMAND_LOG"
    printf ' %q' "$@" >>"$AGENTCLI_TEST_COMMAND_LOG"
    printf '\n' >>"$AGENTCLI_TEST_COMMAND_LOG"
fi

if [[ "${1:-}" == "build" ]]; then
    # Fake uv build --wheel by creating the wheel artifact the app bundles.
    OUT_DIR=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --out-dir|-o)
                OUT_DIR="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    if [[ -z "$OUT_DIR" ]]; then
        printf 'fake uv build requires --out-dir\n' >&2
        exit 1
    fi
    mkdir -p "$OUT_DIR"
    touch "$OUT_DIR/agent_cli-0.0.0-py3-none-any.whl"
    exit 0
fi

if [[ "${1:-}" == "tool" && "${2:-}" == "install" ]]; then
    mkdir -p "${UV_TOOL_BIN_DIR:?}"
    cat >"$UV_TOOL_BIN_DIR/agent-cli" <<'FAKE_AGENT_CLI'
#!/usr/bin/env bash
set -euo pipefail

printf 'agent-cli' >>"$AGENTCLI_TEST_COMMAND_LOG"
printf ' %q' "$@" >>"$AGENTCLI_TEST_COMMAND_LOG"
printf '\n' >>"$AGENTCLI_TEST_COMMAND_LOG"

start_fake_whisper_listener() {
    python3 - <<'PY' >/dev/null 2>&1 &
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 10300))
    sock.listen(1)
    sock.settimeout(30)
    try:
        conn, _ = sock.accept()
        conn.close()
    except TimeoutError:
        pass
except OSError:
    pass
finally:
    sock.close()
PY
}

case "$*" in
    "daemon install whisper -y")
        start_fake_whisper_listener
        printf 'Installed and started whisper\n'
        ;;
    "daemon status"|"daemon status whisper"|"daemon status whisper --logs 0")
        printf 'whisper: running (pid 123)\n'
        ;;
    "transcribe --toggle --quiet")
        printf 'Recording toggled\n'
        ;;
    "--version")
        printf 'agent-cli-test 0.0.0\n'
        ;;
    *)
        printf 'agent-cli fake: %s\n' "$*"
        ;;
esac
FAKE_AGENT_CLI
    chmod 755 "$UV_TOOL_BIN_DIR/agent-cli"
    printf 'Installed fake agent-cli\n'
    exit 0
fi

printf 'fake uv received unsupported command: %s\n' "$*" >&2
exit 1
FAKE_UV
chmod 755 "$FAKE_UV"

# Exercise build-macos-app.sh --dmg through the install flow.
UV_BINARY="$FAKE_UV" INSTALL_DIR="$INSTALL_DIR" AGENTCLI_SKIP_OPEN=1 \
    "$ROOT_DIR/macos/build-macos-app.sh" --install --dmg

test -x "$APP/Contents/MacOS/AgentCLI"
test -x "$APP/Contents/Resources/bin/uv"
test -f "$APP/Contents/Resources/logo-avatar.svg"
test -f "$APP/Contents/Resources/logo-avatar.png"
test -f "$APP/Contents/Resources/AgentCLI.icns"
test -f "$APP/Contents/Resources/wheels/agent_cli-0.0.0-py3-none-any.whl"
codesign --verify --verbose=2 "$APP"
hdiutil verify "$DMG"

SUPPORT_DIR="$TMP_DIR/Application Support/AgentCLI"
SELF_TEST_OUTPUT=$(
    AGENTCLI_APP_SUPPORT_DIR="$SUPPORT_DIR" \
        "$APP/Contents/MacOS/AgentCLI" --agentcli-self-test
)

case "$SELF_TEST_OUTPUT" in
    *"AgentCLI self-test ok"*) ;;
    *)
        echo "$SELF_TEST_OUTPUT" >&2
        echo "AgentCLI self-test did not report success" >&2
        exit 1
        ;;
esac

BOOTSTRAP_TEST_OUTPUT=$(
    AGENTCLI_TEST_COMMAND_LOG="$COMMAND_LOG" \
        AGENTCLI_APP_SUPPORT_DIR="$SUPPORT_DIR" \
        "$APP/Contents/MacOS/AgentCLI" --agentcli-bootstrap-self-test
)

case "$BOOTSTRAP_TEST_OUTPUT" in
    *"AgentCLI bootstrap self-test ok"*) ;;
    *)
        echo "$BOOTSTRAP_TEST_OUTPUT" >&2
        echo "AgentCLI bootstrap self-test did not report success" >&2
        exit 1
        ;;
esac

grep -F "uv tool install" "$COMMAND_LOG"
grep -F "agent-cli daemon install whisper -y" "$COMMAND_LOG"
grep -F "agent-cli transcribe --toggle --quiet" "$COMMAND_LOG"

AGENTCLI_TEST_COMMAND_LOG="$COMMAND_LOG" \
    AGENTCLI_INSTANCE_LOCK_PATH="$TMP_DIR/agentcli.lock" \
    AGENTCLI_APP_SUPPORT_DIR="$SUPPORT_DIR" \
    "$APP/Contents/MacOS/AgentCLI" &
APP_PID=$!
sleep 2
kill -0 "$APP_PID"
kill "$APP_PID" >/dev/null 2>&1 || true
wait "$APP_PID" >/dev/null 2>&1 || true

echo "macOS app E2E passed: $APP"
