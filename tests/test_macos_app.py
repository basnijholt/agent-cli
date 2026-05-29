"""Tests for the native macOS menu bar wrapper packaging."""

from __future__ import annotations

import plistlib
import re
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
MACOS_APP = ROOT / "macos" / "AgentCLI"
SWIFT_SOURCE_DIR = MACOS_APP / "Sources" / "AgentCLI"
BUILD_SCRIPT = ROOT / "macos" / "build-macos-app.sh"
E2E_SCRIPT = ROOT / "macos" / "test-macos-app-e2e.sh"
LOGO_SVG = ROOT / "docs" / "logo-clean.svg"
MENU_BAR_LOGO_SVG = ROOT / "docs" / "logo-avatar.svg"


def assert_script_executable(path: Path) -> None:
    """Assert shell scripts are executable, allowing Windows checkout mode loss."""
    if path.stat().st_mode & stat.S_IXUSR:
        return

    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "ls-files", "-s", "--", path.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.startswith("100755 ")


def test_macos_app_package_files_exist() -> None:
    """The menu bar wrapper should live in a self-contained Swift package."""
    assert (MACOS_APP / "Package.swift").is_file()
    for filename in (
        "AgentCLIApp.swift",
        "AgentCommand.swift",
        "AgentCommandRunner.swift",
        "AgentRuntime.swift",
        "AppDelegate.swift",
        "BootstrapState.swift",
        "CommandResult.swift",
        "ConfigurableHotkeyController.swift",
        "FocusedTextTarget.swift",
        "MenuBarIcon.swift",
        "MenuActivityStatus.swift",
        "MenuActivityStatusRow.swift",
        "MenuActivityTracker.swift",
        "RecordingIndicatorController.swift",
        "SettingsWindowController.swift",
        "Shortcuts.swift",
        "StatusMenuController.swift",
        "TranscriptPasteController.swift",
        "VoiceLevelOverlay.swift",
    ):
        assert (SWIFT_SOURCE_DIR / filename).is_file()
    assert (MACOS_APP / "Resources" / "Info.plist").is_file()
    assert (MACOS_APP / "README.md").is_file()
    assert LOGO_SVG.is_file()
    assert MENU_BAR_LOGO_SVG.is_file()


def test_macos_app_depends_on_keyboardshortcuts_package() -> None:
    """KeyboardShortcuts README documents SPM install from this URL."""
    package = (MACOS_APP / "Package.swift").read_text(encoding="utf-8")

    assert "https://github.com/sindresorhus/KeyboardShortcuts" in package
    assert 'exact: "1.10.0"' in package
    assert '.product(name: "KeyboardShortcuts", package: "KeyboardShortcuts")' in package


def test_macos_app_has_swift_unit_test_target() -> None:
    """Pure macOS app behavior should have an XCTest target."""
    package = (MACOS_APP / "Package.swift").read_text(encoding="utf-8")
    tests = (MACOS_APP / "Tests" / "AgentCLITests" / "AgentCommandTests.swift").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")

    assert ".testTarget(" in package
    assert 'name: "AgentCLITests"' in package
    assert 'dependencies: ["AgentCLI"]' in package
    assert (MACOS_APP / "Tests" / "AgentCLITests" / "AgentCommandTests.swift").is_file()
    assert "final class AgentCommandTests: XCTestCase" in tests
    assert "testToggleTranscriptionUsesTypedArgumentsAndTranscriptionBootstrap" in tests
    assert "swift test --package-path macos/AgentCLI --enable-xctest" in workflow


def test_macos_app_exposes_transcription_log_from_menu() -> None:
    """Recorded transcriptions should be logged and the log should be openable."""
    command = (SWIFT_SOURCE_DIR / "AgentCommand.swift").read_text(encoding="utf-8")
    reader = (SWIFT_SOURCE_DIR / "RecentTranscriptionReader.swift").read_text(encoding="utf-8")
    runner = (SWIFT_SOURCE_DIR / "AgentCommandRunner.swift").read_text(encoding="utf-8")
    menu = (SWIFT_SOURCE_DIR / "StatusMenuController.swift").read_text(encoding="utf-8")

    assert '"--transcription-log"' in command
    assert "RecentTranscriptionReader.defaultLogPath" in command
    assert 'static let defaultLogPath = "~/.config/agent-cli/transcriptions.jsonl"' in reader
    assert "static var defaultLogURL: URL" in reader
    assert "func openTranscriptionLog()" in runner
    assert "RecentTranscriptionReader.defaultLogURL" in runner
    assert '"Open Transcription Log"' in menu
    assert "#selector(openTranscriptionLog)" in menu


def test_macos_info_plist_declares_menu_bar_agent_app() -> None:
    """The app bundle should be installable and hidden from the Dock."""
    with (MACOS_APP / "Resources" / "Info.plist").open("rb") as f:
        plist = plistlib.load(f)

    assert plist["CFBundleExecutable"] == "AgentCLI"
    assert plist["CFBundleIdentifier"] == "lt.nijho.agent-cli.menubar"
    assert plist["CFBundleIconFile"] == "AgentCLI"
    assert plist["CFBundlePackageType"] == "APPL"
    assert plist["LSUIElement"] is True
    assert "microphone" in plist["NSMicrophoneUsageDescription"].lower()


def test_macos_app_signing_declares_audio_input_entitlement() -> None:
    """Developer ID hardened runtime builds need audio-input entitlement for mic capture."""
    entitlements_path = MACOS_APP / "Resources" / "AgentCLI.entitlements"
    with entitlements_path.open("rb") as f:
        entitlements = plistlib.load(f)
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert entitlements["com.apple.security.device.audio-input"] is True
    assert 'ENTITLEMENTS_PLIST="$PACKAGE_DIR/Resources/AgentCLI.entitlements"' in script
    assert "--entitlements" in script
    assert '"$ENTITLEMENTS_PLIST"' in script
    assert '[[ ! -f "$ENTITLEMENTS_PLIST" ]]' in script


def test_macos_build_script_creates_signed_app_bundle() -> None:
    """The build script should produce a Finder-installable .app bundle."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert_script_executable(BUILD_SCRIPT)
    assert "swift build" in script
    assert "Contents/MacOS" in script
    assert "Contents/Info.plist" in script
    assert "CFBundleIconFile" not in script
    assert "Contents/Resources/AgentCLI.icns" in script
    assert "Contents/Resources/logo-avatar.png" in script
    assert "iconutil" in script
    assert "qlmanage" in script
    assert "sips" in script
    assert "Contents/Resources/bin/uv" in script
    assert "Contents/Resources/wheels" in script
    assert "uv build --wheel" in script
    assert "agent_cli-*.whl" in script
    assert "command -v uv" in script
    assert "INSTALL_DIR" in script
    assert "AGENTCLI_SKIP_OPEN" in script
    assert "quit_running_app" in script
    assert 'pgrep -x "$APP_NAME"' in script
    assert 'osascript -e "quit app \\"$APP_NAME\\""' in script
    assert 'ditto "$APP_DIR" "$INSTALL_PATH"' in script
    assert "Installed AgentCLI notification logo is missing" in script
    assert "codesign" in script
    assert "--deep" in script
    assert "--install" in script
    assert "--dmg" in script
    assert "hdiutil create" in script


def test_macos_build_script_stamps_release_version_into_app_bundle() -> None:
    """Released app bundles should not keep the static template plist version."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "APP_VERSION" in script
    assert "BUILD_VERSION" in script
    assert "resolve_app_version" in script
    assert "resolve_build_version" in script
    assert "stamp_info_plist" in script
    assert "/usr/libexec/PlistBuddy" in script
    assert "CFBundleShortVersionString" in script
    assert "CFBundleVersion" in script
    assert 'stamp_info_plist "$(basename "$WHEEL_PATH")"' in script
    assert script.index('stamp_info_plist "$(basename "$WHEEL_PATH")"') < script.index(
        'sign_app "$APP_DIR"',
    )


def test_macos_build_script_can_notarize_release_dmg() -> None:
    """Release builds should notarize and staple a Developer ID-signed DMG."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "NOTARIZE" in script
    assert "APPLE_ID" in script
    assert "APPLE_APP_SPECIFIC_PASSWORD" in script
    assert "APPLE_TEAM_ID" in script
    assert "NOTARY_TIMEOUT_SECONDS" in script
    assert "NOTARY_POLL_INTERVAL_SECONDS" in script
    assert "xcrun notarytool submit" in script
    assert "xcrun notarytool info" in script
    assert "xcrun notarytool log" in script
    assert "Accepted" in script
    assert "In Progress" in script
    assert "--wait" not in script
    assert "xcrun stapler staple" in script
    assert "xcrun stapler validate" in script
    assert "--timestamp" in script
    assert "--options runtime" in script
    assert "Developer ID signing identity" in script


def test_macos_build_script_signs_bundled_executables_before_notarization() -> None:
    """Every executable shipped inside the app bundle must be signed for notarization."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "sign_bundled_executables" in script
    assert 'sign_executable "$APP_DIR/Contents/Resources/bin/uv"' in script
    assert script.index('sign_executable "$APP_DIR/Contents/Resources/bin/uv"') < script.index(
        'sign_app "$APP_DIR"',
    )


def test_macos_build_script_creates_drag_install_dmg() -> None:
    """The release DMG should open as a drag-to-Applications installer window."""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'DMG_STAGING_DIR="$DIST_DIR/dmg-staging"' in script
    assert 'DMG_RW_PATH="$DIST_DIR/$APP_NAME-rw.dmg"' in script
    assert 'DMG_BACKGROUND_SVG="$PACKAGE_DIR/Resources/dmg-background.svg"' in script
    assert 'DMG_BACKGROUND_PNG="$DIST_DIR/dmg-background.png"' in script
    assert 'ln -s /Applications "$DMG_STAGING_DIR/Applications"' in script
    assert '"$DMG_STAGING_DIR/$APP_NAME.app"' in script
    assert 'hdiutil create "$DMG_RW_PATH"' in script
    assert '-size "${image_size_mb}m"' in script
    assert "-fs HFS+" in script
    assert "hdiutil attach" in script
    assert "-mountpoint" not in script
    assert "volume_path=$(printf" in script
    assert 'ditto "$DMG_STAGING_DIR" "$volume_path"' in script
    assert (
        'set background picture of theViewOptions to file ".background:dmg-background.png"'
        in script
    )
    assert 'set position of item "AgentCLI.app" of container window to {150, 180}' in script
    assert 'set position of item "Applications" of container window to {450, 180}' in script
    assert 'if ! set_dmg_finder_layout "$volume_path"; then' in script
    assert "hdiutil convert" in script
    assert "-format UDZO" in script
    assert "sign_dmg_if_needed" in script
    assert (MACOS_APP / "Resources" / "dmg-background.svg").is_file()


def test_release_workflow_publishes_macos_app_asset() -> None:
    """Publishing a GitHub release should attach the notarized macOS DMG."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.startswith("name: Publish Release\n")
    assert "name: Upload Python Package" not in workflow
    assert "name: Publish Python package" in workflow
    assert "name: Build and publish macOS app" in workflow
    assert "build_macos_app" in workflow
    assert re.search(
        r"build_macos_app:\n\s+name: Build and publish macOS app\n\s+runs-on: macos-latest",
        workflow,
    )
    assert "timeout-minutes: 45" in workflow
    assert "contents: write" in workflow
    assert "MACOS_CODESIGN_CERTIFICATE_BASE64" in workflow
    assert "MACOS_CODESIGN_CERTIFICATE_PASSWORD" in workflow
    assert "MACOS_KEYCHAIN_PASSWORD" in workflow
    assert "APPLE_ID" in workflow
    assert "APPLE_APP_SPECIFIC_PASSWORD" in workflow
    assert "APPLE_TEAM_ID" in workflow
    assert "APP_VERSION: ${{ github.event.release.tag_name }}" in workflow
    assert "BUILD_VERSION: ${{ github.run_number }}" in workflow
    assert "apple-actions/import-codesign-certs@v7" in workflow
    assert "p12-file-base64: ${{ secrets.MACOS_CODESIGN_CERTIFICATE_BASE64 }}" in workflow
    assert "p12-password: ${{ secrets.MACOS_CODESIGN_CERTIFICATE_PASSWORD }}" in workflow
    assert "security create-keychain" not in workflow
    assert "security import" not in workflow
    assert "macos/build-macos-app.sh --dmg" in workflow
    assert "NOTARIZE=1" in workflow
    assert "gh release upload" in workflow
    assert "dist/macos/AgentCLI.dmg" in workflow
    assert "python3 .github/scripts/normalize_appcast.py macos/appcast.xml" in workflow
    assert workflow.index(
        "python3 .github/scripts/normalize_appcast.py macos/appcast.xml"
    ) < workflow.index("if git diff --quiet -- Casks/agent-cli.rb macos/appcast.xml; then")


def test_macos_app_has_end_to_end_packaging_test() -> None:
    """The installable artifact should have a repeatable local E2E gate."""
    script = E2E_SCRIPT.read_text(encoding="utf-8")

    assert_script_executable(E2E_SCRIPT)
    assert "build-macos-app.sh --dmg" in script
    assert "INSTALL_DIR=" in script
    assert "AGENTCLI_SKIP_OPEN=1" in script
    assert "codesign --verify" in script
    assert "hdiutil verify" in script
    assert "Contents/Resources/bin/uv" in script
    assert "Contents/Resources/wheels" in script
    assert "Contents/Resources/AgentCLI.icns" in script
    assert "Contents/Resources/logo-avatar.png" in script
    assert "AGENTCLI_TEST_COMMAND_LOG" in script
    assert "AGENTCLI_INSTANCE_LOCK_PATH" in script
    assert "UV_BINARY=" in script
    assert "uv build --wheel" in script
    assert 'test -d "$DMG_MOUNT/AgentCLI.app"' in script
    assert 'test -L "$DMG_MOUNT/Applications"' in script
    assert 'readlink "$DMG_MOUNT/Applications"' in script
    assert 'test -f "$DMG_MOUNT/.background/dmg-background.png"' in script
    assert "--agentcli-bootstrap-self-test" in script
    assert "daemon install whisper -y" in script
    assert "transcribe --toggle --quiet" in script
    assert "open -n" in script or "Contents/MacOS/AgentCLI" in script
