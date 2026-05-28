# Agent CLI macOS app

This directory contains a native SwiftUI menu bar wrapper for `agent-cli`.
The app does not reimplement any agent behavior. It bundles `uv`, installs a
private `agent-cli[audio,llm]` tool into the user's Application Support
directory on first use, and shells out to that private executable.

Transcription is the default zero-config path. The first transcription action
installs and starts the local Whisper launchd daemon with
`agent-cli daemon install whisper -y`; the model is downloaded lazily by the
server on first transcription request. No existing `agent-cli` config file is
required.

The packaged app registers native macOS global hotkeys itself:

- `Fn+Space` toggles transcription
- `Fn` records while held and inserts the transcript
- `Cmd+Shift+A` autocorrects clipboard text
- `Cmd+Shift+V` starts voice edit

Choose **Keyboard Shortcuts...** from the menu bar app to change these
shortcuts. The settings UI uses the `KeyboardShortcuts` Swift package for
shortcut parsing, `UserDefaults` storage, and global key-up handlers.

## Build

From the repository root:

```bash
./macos/build-macos-app.sh
```

The app bundle is written to `dist/macos/AgentCLI.app`.

## Install locally

```bash
./macos/build-macos-app.sh --install
```

This builds the app, copies it to `/Applications/AgentCLI.app`, and opens it.

## Build a DMG

```bash
./macos/build-macos-app.sh --dmg
```

The DMG is written to `dist/macos/AgentCLI.dmg`.

## End-to-end packaging check

```bash
./macos/test-macos-app-e2e.sh
```

The E2E test builds the app and DMG, verifies code signing and the image, then
uses a fake bundled `uv` to prove the app bootstraps its private CLI, installs
the Whisper daemon, and runs the default transcription command without network
downloads.

## Signing

By default the script ad-hoc signs the local app bundle. For public
distribution, pass a Developer ID identity and then notarize the resulting app
or DMG:

```bash
CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" ./macos/build-macos-app.sh --dmg
```

To notarize during the build, set `NOTARIZE=1` and provide Apple notary
credentials:

```bash
CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
NOTARIZE=1 \
APPLE_ID="you@example.com" \
APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx" \
APPLE_TEAM_ID="TEAMID" \
./macos/build-macos-app.sh --dmg
```

## Release CI

Publishing a GitHub release runs `.github/workflows/release.yml`, which imports
the Developer ID certificate with `apple-actions/import-codesign-certs`, builds,
notarizes, staples, and uploads `dist/macos/AgentCLI.dmg` to the release. The
workflow expects these repository secrets:

- `MACOS_CODESIGN_CERTIFICATE_BASE64`: base64-encoded Developer ID Application
  `.p12` certificate export
- `MACOS_CODESIGN_CERTIFICATE_PASSWORD`: password for that `.p12`
- `MACOS_KEYCHAIN_PASSWORD`: temporary CI keychain password
- `APPLE_ID`: Apple ID email for notarization
- `APPLE_APP_SPECIFIC_PASSWORD`: app-specific password for `notarytool`
- `APPLE_TEAM_ID`: Apple Developer Team ID
