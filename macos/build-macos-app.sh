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

codesign --force --deep --sign "$CODESIGN_IDENTITY" "$APP_DIR"

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
    echo "Built $DMG_PATH"
fi

if [[ "$INSTALL" == true ]]; then
    INSTALL_PATH="$INSTALL_DIR/$APP_NAME.app"
    mkdir -p "$INSTALL_DIR"
    rm -rf "$INSTALL_PATH"
    cp -R "$APP_DIR" "$INSTALL_PATH"
    if [[ "${AGENTCLI_SKIP_OPEN:-0}" != "1" ]]; then
        open "$INSTALL_PATH"
        echo "Installed and opened $INSTALL_PATH"
    else
        echo "Installed $INSTALL_PATH"
    fi
fi
