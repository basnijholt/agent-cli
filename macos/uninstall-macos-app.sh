#!/bin/sh

# Run from Contents/Resources before removing this app bundle.
# The standalone CLI can share this service, so verify the installing runtime.
set -eu

resources=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
plist="$HOME/Library/LaunchAgents/com.agent_cli.whisper.plist"
owner=$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:AGENTCLI_BUNDLED_UV' "$plist" 2>/dev/null) || exit 0
[ "$owner" = "$resources/bin/uv" ] || exit 0

service="gui/$(/usr/bin/id -u)/com.agent_cli.whisper"
if job=$(/bin/launchctl print "$service" 2>/dev/null); then
    # The loaded job can differ from a newly written plist. launchctl(1) warns
    # that print is not a stable API: require the known structure and refuse
    # cleanup if it changes. Inherited environment alone is not ownership.
    if ! printf '%s\n' "$job" | AGENTCLI_EXPECTED_UV="$resources/bin/uv" /usr/bin/awk '
        BEGIN { expected = ENVIRON["AGENTCLI_EXPECTED_UV"] }
        /^\tprogram = / { programs++; owned_program += ($0 == "\tprogram = " expected) }
        $0 == "\tenvironment = {" { in_environment = 1; environments++; next }
        in_environment && $0 == "\t}" { in_environment = 0 }
        in_environment && /^\t\tAGENTCLI_BUNDLED_UV => / {
            owners++
            owned_environment += ($0 == "\t\tAGENTCLI_BUNDLED_UV => " expected)
        }
        END { exit !(programs == 1 && owned_program == 1 && environments == 1 &&
                     owners == 1 && owned_environment == 1 && !in_environment) }
    '; then
        echo "Cannot confirm ownership of the loaded Whisper service; leaving it intact." >&2
        exit 1
    fi
    /bin/launchctl bootout "$service" || exit $?
    # bootout returns before a slow process has finished handling SIGTERM.
    # Keep the plist until launchd confirms that the job has disappeared.
    deadline=$(( $(/bin/date +%s) + 30 ))
    while :; do
        if /bin/launchctl print "$service" >/dev/null 2>&1; then
            if [ "$(/bin/date +%s)" -ge "$deadline" ]; then
                echo "Whisper service did not stop within 30 seconds; leaving its plist intact." >&2
                exit 1
            fi
            /bin/sleep 1
        else
            status=$?
            [ "$status" -eq 113 ] && break
            echo "Cannot verify Whisper service shutdown; leaving its plist intact." >&2
            exit "$status"
        fi
    done
else
    status=$?
    # launchctl error 113: Could not find specified service.
    if [ "$status" -ne 113 ]; then
        echo "Cannot query the Whisper service; leaving its plist intact." >&2
        exit "$status"
    fi
fi
/bin/rm -f "$plist"
