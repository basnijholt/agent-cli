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
- Accessibility permission for Fn shortcuts and inserting text into other apps

## Install with Homebrew

Install the signed app release with the Homebrew cask:

```bash
brew install --cask basnijholt/tap/agent-cli
```

Then open **AgentCLI** from `/Applications` or Spotlight.

## First Launch

1. Open **AgentCLI**. The Permissions page opens on first launch if microphone access is missing.
2. Choose **Allow…** for Microphone, then approve the macOS request.
3. To use Fn shortcuts and automatic text insertion, choose **Open System Settings…** for Accessibility and enable Agent CLI. Notifications are optional.
4. Return to Agent CLI to refresh permission status, then use the menu bar icon to start recording or open Settings.

Permission checks never trigger a prompt on their own. If access was previously denied, the Permissions page opens the relevant System Settings page instead of requesting it again. You can reopen **Settings… > Permissions** at any time and choose **Check Again** to refresh status.

If Accessibility is enabled in System Settings but not in the app, quit and reopen Agent CLI and check that you enabled the running copy. The **Still having trouble?** section shows the app's location and offers a confirmation-gated Accessibility reset as a last resort.

The first transcription can take longer because AgentCLI installs the private CLI runtime, ensures the Whisper launchd daemon is available, and downloads the speech model lazily.

## Default Shortcuts

| Shortcut | Action |
|----------|--------|
| `Fn+Space` | Toggle transcription |
| `Fn` | Record while held and insert the transcript |
| `Cmd+Shift+A` | Autocorrect clipboard text |
| `Cmd+Shift+V` | Start voice edit |

Open **Settings… > Shortcuts** to change shortcuts. **Start at login** is in General; runtime choices and diagnostics are in Advanced.

## Live Transcription Preview

The menu bar app can show provisional transcription text above the recording meter while you speak. Enable **Show live transcription preview** in **Settings… > Recording** to turn it on.

This setting is off by default. When enabled, AgentCLI writes rolling preview events to `~/.config/agent-cli/live-preview.jsonl` and updates the overlay during toggle or hold-to-transcribe recordings. Preview text is best-effort and may revise earlier words as more audio arrives; the final transcript is still produced and inserted after recording stops.

## Runtime Modes

By default, the app manages its own private `agent-cli` install so the menu bar workflow is zero-config and does not depend on your shell PATH.

If you already manage `agent-cli` yourself, enable **Use my installed agent-cli** in **Settings… > Advanced**. AgentCLI will then run the `agent-cli` executable found on PATH and use your normal configuration.

## Updates

The app uses Sparkle for direct updates. Choose **Check for Updates…** from the menu bar app or **Settings… > General** to check for a newer signed release.

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
