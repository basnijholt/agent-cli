#!/usr/bin/env bash

set -euo pipefail

APP_NAME="AgentCLI"
DISPLAY_NAME="Agent CLI"
INSTALL=false
CREATE_DMG=false

usage() {
    cat <<'EOF'
Usage: macos/build-macos-app.sh [--install] [--dmg]

Build the native macOS menu bar app for agent-cli.

Options:
  --install   Copy the built app to /Applications and open it.
  --dmg       Create dist/macos/AgentCLI.dmg.
  -h, --help  Show this help text.

Environment:
  CODESIGN_IDENTITY  Codesign identity to use. Defaults to ad-hoc signing (-).
  UV_BINARY          uv binary to bundle. Defaults to the uv found on PATH.
  INSTALL_DIR        Install destination. Defaults to /Applications.
  AGENTCLI_SKIP_OPEN Set to 1 to skip opening the app after --install.
  NOTARIZE           Set to 1 to notarize and staple the DMG. Requires --dmg.
  APPLE_ID           Apple ID email used for notarization.
  APPLE_APP_SPECIFIC_PASSWORD
                     App-specific password used by xcrun notarytool.
  APPLE_TEAM_ID      Apple Developer Team ID used for notarization.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)
            INSTALL=true
            shift
            ;;
        --dmg)
            CREATE_DMG=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PACKAGE_DIR="$ROOT_DIR/macos/$APP_NAME"
DIST_DIR="$ROOT_DIR/dist/macos"
APP_DIR="$DIST_DIR/$APP_NAME.app"
WHEEL_BUILD_DIR="$DIST_DIR/wheels-build"
INFO_PLIST="$PACKAGE_DIR/Resources/Info.plist"
MENU_BAR_LOGO_SVG="$ROOT_DIR/docs/logo-avatar.svg"
ICONSET_DIR="$DIST_DIR/AgentCLI.iconset"
ICON_SOURCE_PNG="$DIST_DIR/logo-avatar-source.png"
NOTIFICATION_LOGO_PNG="$DIST_DIR/logo-avatar.png"
APP_ICON_ICNS="$DIST_DIR/AgentCLI.icns"
CODESIGN_IDENTITY=${CODESIGN_IDENTITY:--}
UV_BINARY=${UV_BINARY:-$(command -v uv || true)}
INSTALL_DIR=${INSTALL_DIR:-/Applications}
NOTARIZE=${NOTARIZE:-0}

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script builds a macOS .app bundle and must run on macOS." >&2
    exit 1
fi

if ! command -v swift >/dev/null 2>&1; then
    echo "swift is required. Install Xcode or the Xcode Command Line Tools." >&2
    exit 1
fi

for required_tool in qlmanage sips iconutil; do
    if ! command -v "$required_tool" >/dev/null 2>&1; then
        echo "$required_tool is required to build the AgentCLI app icon." >&2
        exit 1
    fi
done

if [[ -z "$UV_BINARY" || ! -x "$UV_BINARY" ]]; then
    echo "uv is required so it can be bundled into the app. Set UV_BINARY or install uv." >&2
    exit 1
fi

if [[ ! -f "$MENU_BAR_LOGO_SVG" ]]; then
    echo "AgentCLI menu bar logo SVG is missing: $MENU_BAR_LOGO_SVG" >&2
    exit 1
fi

if [[ "$NOTARIZE" == "1" && "$CREATE_DMG" != true ]]; then
    echo "NOTARIZE=1 requires --dmg so there is a distributable artifact to notarize." >&2
    exit 1
fi

codesign_args() {
    printf '%s\0' --force --sign "$CODESIGN_IDENTITY"
    if [[ "$CODESIGN_IDENTITY" != "-" ]]; then
        printf '%s\0' --timestamp --options runtime
    fi
}

sign_executable() {
    local target="$1"
    local args=()
    while IFS= read -r -d '' arg; do
        args+=("$arg")
    done < <(codesign_args)

    codesign "${args[@]}" "$target"
}

sign_bundled_executables() {
    sign_executable "$APP_DIR/Contents/Resources/bin/uv"
}

sign_app() {
    local target="$1"
    local args=()
    while IFS= read -r -d '' arg; do
        args+=("$arg")
    done < <(codesign_args)

    codesign --deep "${args[@]}" "$target"
}

sign_dmg_if_needed() {
    local dmg_path="$1"
    if [[ "$CODESIGN_IDENTITY" == "-" ]]; then
        return
    fi

    codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$dmg_path"
}

require_notarization_env() {
    if [[ "$CODESIGN_IDENTITY" == "-" ]]; then
        echo "A Developer ID signing identity is required when NOTARIZE=1." >&2
        exit 1
    fi

    for variable in APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
        if [[ -z "${!variable:-}" ]]; then
            echo "$variable is required when NOTARIZE=1." >&2
            exit 1
        fi
    done
}

notarize_dmg() {
    local dmg_path="$1"
    local notary_result="$DIST_DIR/notary-submit.json"
    local submission_id
    local status

    require_notarization_env
    echo "Submitting $dmg_path for Apple notarization..."
    if ! xcrun notarytool submit "$dmg_path" \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait \
        --output-format json | tee "$notary_result"; then
        echo "Apple notarization submission failed." >&2
        exit 1
    fi

    submission_id=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("id", ""))' "$notary_result")
    status=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("status", ""))' "$notary_result")
    if [[ "$status" != "Accepted" ]]; then
        echo "Apple notarization failed with status: ${status:-unknown}." >&2
        if [[ -n "$submission_id" ]]; then
            xcrun notarytool log "$submission_id" \
                --apple-id "$APPLE_ID" \
                --password "$APPLE_APP_SPECIFIC_PASSWORD" \
                --team-id "$APPLE_TEAM_ID" >&2 || true
        fi
        exit 1
    fi

    xcrun stapler staple "$dmg_path"
    xcrun stapler validate "$dmg_path"
    echo "Notarized and stapled $dmg_path"
}

render_logo_png() {
    local size="$1"
    local destination="$2"
    local render_dir="$DIST_DIR/icon-render-$size"
    local rendered="$render_dir/$(basename "$MENU_BAR_LOGO_SVG").png"

    rm -rf "$render_dir"
    mkdir -p "$render_dir"
    qlmanage -t -s "$size" -o "$render_dir" "$MENU_BAR_LOGO_SVG" >/dev/null 2>&1
    if [[ ! -f "$rendered" ]]; then
        echo "Failed to render AgentCLI logo PNG: $rendered" >&2
        exit 1
    fi
    cp "$rendered" "$destination"
    rm -rf "$render_dir"
}

build_app_icon() {
    rm -rf "$ICONSET_DIR" "$ICON_SOURCE_PNG" "$NOTIFICATION_LOGO_PNG" "$APP_ICON_ICNS"
    mkdir -p "$ICONSET_DIR"

    render_logo_png 1024 "$ICON_SOURCE_PNG"
    cp "$ICON_SOURCE_PNG" "$NOTIFICATION_LOGO_PNG"

    sips -z 16 16 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
    sips -z 64 64 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$ICON_SOURCE_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
    cp "$ICON_SOURCE_PNG" "$ICONSET_DIR/icon_512x512@2x.png"

    iconutil -c icns "$ICONSET_DIR" -o "$APP_ICON_ICNS"
    rm -rf "$ICONSET_DIR"
}

quit_running_app() {
    if ! pgrep -x "$APP_NAME" >/dev/null 2>&1; then
        return
    fi

    osascript -e "quit app \"$APP_NAME\"" >/dev/null 2>&1 || true
    for _ in {1..20}; do
        if ! pgrep -x "$APP_NAME" >/dev/null 2>&1; then
            return
        fi
        sleep 0.2
    done

    pkill -x "$APP_NAME" >/dev/null 2>&1 || true
    for _ in {1..20}; do
        if ! pgrep -x "$APP_NAME" >/dev/null 2>&1; then
            return
        fi
        sleep 0.2
    done

    echo "Timed out waiting for $APP_NAME to quit before install." >&2
    exit 1
}

echo "Building $DISPLAY_NAME..."
swift build -c release --package-path "$PACKAGE_DIR"
BIN_DIR=$(swift build -c release --package-path "$PACKAGE_DIR" --show-bin-path)
BINARY="$BIN_DIR/$APP_NAME"

if [[ ! -x "$BINARY" ]]; then
    echo "Built binary not found: $BINARY" >&2
    exit 1
fi

echo "Building agent-cli wheel..."
# uv build --wheel keeps the app tied to this source checkout instead of a remote release.
rm -rf "$WHEEL_BUILD_DIR"
"$UV_BINARY" build --wheel --out-dir "$WHEEL_BUILD_DIR" "$ROOT_DIR"
WHEEL_PATH=$(find "$WHEEL_BUILD_DIR" -maxdepth 1 -name 'agent_cli-*.whl' -print -quit)
if [[ -z "$WHEEL_PATH" || ! -f "$WHEEL_PATH" ]]; then
    echo "Built wheel not found: $WHEEL_BUILD_DIR/agent_cli-*.whl" >&2
    exit 1
fi

echo "Building app icon..."
build_app_icon

rm -rf "$APP_DIR"
mkdir -p \
    "$APP_DIR/Contents/MacOS" \
    "$APP_DIR/Contents/Resources/bin" \
    "$APP_DIR/Contents/Resources/wheels"

cp "$BINARY" "$APP_DIR/Contents/MacOS/$APP_NAME"
cp "$INFO_PLIST" "$APP_DIR/Contents/Info.plist"
cp "$UV_BINARY" "$APP_DIR/Contents/Resources/bin/uv"
cp "$WHEEL_PATH" "$APP_DIR/Contents/Resources/wheels/"
cp "$MENU_BAR_LOGO_SVG" "$APP_DIR/Contents/Resources/logo-avatar.svg"
cp "$NOTIFICATION_LOGO_PNG" "$APP_DIR/Contents/Resources/logo-avatar.png"
cp "$APP_ICON_ICNS" "$APP_DIR/Contents/Resources/AgentCLI.icns"
chmod 755 "$APP_DIR/Contents/MacOS/$APP_NAME"
chmod 755 "$APP_DIR/Contents/Resources/bin/uv"

test -x "$APP_DIR/Contents/Resources/bin/uv" || {
    echo "Bundled uv is missing or not executable: $APP_DIR/Contents/Resources/bin/uv" >&2
    exit 1
}

test -f "$APP_DIR/Contents/Resources/wheels/$(basename "$WHEEL_PATH")" || {
    echo "Bundled wheel is missing: $APP_DIR/Contents/Resources/wheels/$(basename "$WHEEL_PATH")" >&2
    exit 1
}

test -f "$APP_DIR/Contents/Resources/logo-avatar.svg" || {
    echo "Bundled AgentCLI logo is missing: $APP_DIR/Contents/Resources/logo-avatar.svg" >&2
    exit 1
}

test -f "$APP_DIR/Contents/Resources/logo-avatar.png" || {
    echo "Bundled AgentCLI notification logo is missing: $APP_DIR/Contents/Resources/logo-avatar.png" >&2
    exit 1
}

test -f "$APP_DIR/Contents/Resources/AgentCLI.icns" || {
    echo "Bundled AgentCLI app icon is missing: $APP_DIR/Contents/Resources/AgentCLI.icns" >&2
    exit 1
}

sign_bundled_executables
sign_app "$APP_DIR"

echo "Built $APP_DIR"

if [[ "$CREATE_DMG" == true ]]; then
    DMG_PATH="$DIST_DIR/$APP_NAME.dmg"
    for attempt in 1 2 3; do
        rm -f "$DMG_PATH"
        if hdiutil create \
            -volname "$DISPLAY_NAME" \
            -srcfolder "$APP_DIR" \
            -ov \
            -format UDZO \
            "$DMG_PATH"; then
            break
        fi
        if [[ "$attempt" == 3 ]]; then
            echo "Failed to build $DMG_PATH after $attempt attempts." >&2
            exit 1
        fi
        sleep 2
    done
    sign_dmg_if_needed "$DMG_PATH"
    if [[ "$NOTARIZE" == "1" ]]; then
        notarize_dmg "$DMG_PATH"
    fi
    echo "Built $DMG_PATH"
fi

if [[ "$INSTALL" == true ]]; then
    INSTALL_PATH="$INSTALL_DIR/$APP_NAME.app"
    mkdir -p "$INSTALL_DIR"
    quit_running_app
    rm -rf "$INSTALL_PATH"
    ditto "$APP_DIR" "$INSTALL_PATH"
    test -f "$INSTALL_PATH/Contents/Resources/logo-avatar.png" || {
        echo "Installed AgentCLI notification logo is missing: $INSTALL_PATH/Contents/Resources/logo-avatar.png" >&2
        exit 1
    }
    codesign --verify --deep --strict "$INSTALL_PATH"
    if [[ "${AGENTCLI_SKIP_OPEN:-0}" != "1" ]]; then
        open "$INSTALL_PATH"
        echo "Installed and opened $INSTALL_PATH"
    else
        echo "Installed $INSTALL_PATH"
    fi
fi
