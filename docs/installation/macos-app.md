---
icon: lucide/panel-top
---

# macOS Menu Bar App

Agent CLI also ships as a native macOS menu bar app for voice workflows that should be available from any app without keeping a terminal open.

The app is a SwiftUI wrapper around the same `agent-cli` commands. It bundles `uv`, installs a private `agent-cli[audio,llm]` runtime in your Application Support folder on first use, and starts the local Whisper daemon automatically the first time you transcribe.

## Requirements

- Apple Silicon Mac
- macOS 13 Ventura or later
- Microphone permission for transcription
- Accessibility permission if you want AgentCLI to insert text into other apps

## Install with Homebrew

Install the signed app release with the Homebrew cask:

```bash
brew install --cask basnijholt/tap/agent-cli
```

Then open **AgentCLI** from `/Applications` or Spotlight.

If you already cloned the repository and want to install the cask from the local checkout:

```bash
brew install --cask ./Casks/agent-cli.rb
```

## First Launch

1. Open **AgentCLI**.
2. Approve macOS microphone permission when prompted.
3. Use the menu bar icon to start transcription, autocorrect clipboard text, or open Settings.
4. Grant Accessibility permission in System Settings if auto-insert or clipboard automation is blocked.

The first transcription can take longer because AgentCLI installs the private CLI runtime, ensures the Whisper launchd daemon is available, and downloads the speech model lazily.

## Default Shortcuts

| Shortcut | Action |
|----------|--------|
| `Fn+Space` | Toggle transcription |
| `Fn` | Record while held and insert the transcript |
| `Cmd+Shift+A` | Autocorrect clipboard text |
| `Cmd+Shift+V` | Start voice edit |

Open **Settings...** from the menu bar app to change shortcuts, enable **Start at Login**, or switch runtime modes.

## Runtime Modes

By default, the app manages its own private `agent-cli` install so the menu bar workflow is zero-config and does not depend on your shell PATH.

If you already manage `agent-cli` yourself, enable **Use User-Installed agent-cli** in Settings. AgentCLI will then run the `agent-cli` executable found on PATH and use your normal configuration.

## Updates

The app uses Sparkle for direct updates. Choose **Check for Updates...** from the menu bar app or Settings to check for a newer signed release.

If you installed with Homebrew, you can also update through Homebrew:

```bash
brew update
brew upgrade --cask agent-cli
```

## Uninstall

```bash
brew uninstall --cask agent-cli
```

To remove app data, launch agents, logs, and preferences as well:

```bash
brew uninstall --zap --cask agent-cli
```

## Build from Source

From the repository root:

```bash
./macos/build-macos-app.sh --install
```

This builds the app, copies it to `/Applications/AgentCLI.app`, and opens it.

For packaging and release details, see the [macOS app README](https://github.com/basnijholt/agent-cli/blob/main/macos/AgentCLI/README.md).
