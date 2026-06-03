# Agent CLI macOS app

This directory contains a native SwiftUI menu bar wrapper for `agent-cli`.
The app does not reimplement any agent behavior. By default, it bundles `uv`,
installs a private `agent-cli[audio,llm]` tool into the user's Application
Support directory on first use, and shells out to that private executable.
Users who already manage their own `agent-cli` install can enable
**Use User-Installed agent-cli** in Settings to run the `agent-cli` found on
PATH with their normal config instead.

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

Choose **Settings...** from the menu bar app to change these shortcuts, enable
**Start at Login**, or switch between the bundled runtime and a user-installed
`agent-cli`. The settings UI uses the `KeyboardShortcuts` Swift package for
shortcut parsing and `UserDefaults` storage. Transcription shortcuts are handled
by a small CGEvent tap so `Fn`, `Fn+Space`, and plain Space remain distinct; the
clipboard utility shortcuts still use `KeyboardShortcuts` global handlers. The
login option uses Apple's login item API for the main app bundle, so macOS may
require approval in System Settings → General → Login Items.

The app uses Sparkle for direct app updates. Release builds stamp
`SUPublicEDKey` into `Info.plist`, publish signed updates in `macos/appcast.xml`,
upload `AgentCLI.zip` for Sparkle, and expose **Check for Updates...** from the
menu bar and Settings. Local builds without a Sparkle public key still run, but
update checks are disabled.

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
SPARKLE_PUBLIC_ED_KEY="public-ed25519-key" \
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
- `SPARKLE_PRIVATE_ED_KEY`: private Sparkle EdDSA key for signing updates
- `HOMEBREW_TAP_DISPATCH_TOKEN`: fine-grained token with Contents write access
  to `basnijholt/homebrew-tap`, used to trigger the tap cask update workflow

The workflow also expects the repository variable `SPARKLE_PUBLIC_ED_KEY`.
Generate the key pair with Sparkle's `generate_keys` tool and store only the
private key as a GitHub secret.
