#!/bin/sh

# Run from Contents/Resources before removing this app bundle.
# The standalone CLI can share this service, so verify the installing runtime.
set -eu

resources=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
plist="$HOME/Library/LaunchAgents/com.agent_cli.whisper.plist"
owner=$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:AGENTCLI_BUNDLED_UV' "$plist" 2>/dev/null) || exit 0
[ "$owner" = "$resources/bin/uv" ] || exit 0

service="gui/$(/usr/bin/id -u)/com.agent_cli.whisper"
if /bin/launchctl print "$service" >/dev/null 2>&1; then
    /bin/launchctl bootout "$service" || exit $?
fi
/bin/rm -f "$plist"
