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

**macOS:**

- Cmd+Shift+R: Toggle voice transcription
- Cmd+Shift+A: Autocorrect clipboard text
- Cmd+Shift+V: Voice edit clipboard text

**Linux:**

- Super+Shift+R: Toggle voice transcription
- Super+Shift+A: Autocorrect clipboard text
- Super+Shift+V: Voice edit clipboard text

On macOS, you may need to grant Accessibility permissions to skhd in System Settings → Privacy & Security → Accessibility.

## Options

| Option | Description |
|--------|-------------|
| `--help`, `-h` | Show help for the command |

## Example

```bash
agent-cli install-hotkeys
```
