---
icon: lucide/keyboard
---

# install-hotkeys

Install system-wide hotkeys for agent-cli commands.

## Usage

```bash
agent-cli install-hotkeys [OPTIONS]
```

## Description

Sets up hotkeys for common workflows:

- Installs missing `audio` and `llm` Python extras first, so transcription and voice-edit hotkeys work without a separate `install-extras` step
- On macOS, also installs `skhd` and `terminal-notifier`
- On Linux, installs notification support if needed and prints desktop-environment-specific bindings

**macOS:**

- Cmd+Shift+1: Toggle voice transcription
- Cmd+Shift+2: Autocorrect clipboard text
- Cmd+Shift+`: Voice edit clipboard text

**Linux:**

- Super+Shift+R: Toggle voice transcription
- Super+Shift+A: Autocorrect clipboard text
- Super+Shift+V: Voice edit clipboard text

On macOS, you may need to grant Accessibility permissions to skhd in System Settings → Privacy & Security → Accessibility.

On a fresh install, `agent-cli install-hotkeys` may take longer than expected because it can download Python extras before setting up the platform-specific scripts.

## Options

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Show help for the command |

## Example

```bash
agent-cli install-hotkeys
```
