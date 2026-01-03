---
icon: lucide/keyboard
---

# System Integration

Set up system-wide hotkeys and integrations for seamless voice-powered workflows.

## Overview

Agent CLI is designed to work with system-wide hotkeys, allowing you to trigger voice commands from any application. This page covers setup for different platforms.

## macOS Setup

### Automated Setup (Recommended)

```bash
agent-cli install-hotkeys
```

This automatically installs all dependencies (skhd, terminal-notifier) and creates a default configuration with common hotkeys. See [`install-hotkeys`](commands/install-hotkeys.md) for all options.

> [!NOTE]
> **Accessibility Permission Required**
>
> After installation, grant Accessibility permissions to skhd:
> System Settings → Privacy & Security → Accessibility → enable "skhd"

### Manual skhd Configuration

Create or edit `~/.config/skhd/skhdrc`:

```bash
# Transcribe to clipboard (toggle recording)
cmd + shift + r : /path/to/agent-cli transcribe --toggle --input-device-index 1

# Autocorrect clipboard
cmd + shift + a : /path/to/agent-cli autocorrect

# Voice edit clipboard
cmd + shift + v : /path/to/agent-cli voice-edit --toggle --input-device-index 1

# Speak clipboard
cmd + shift + s : /path/to/agent-cli speak
```

See: [`transcribe`](commands/transcribe.md), [`autocorrect`](commands/autocorrect.md), [`voice-edit`](commands/voice-edit.md), [`speak`](commands/speak.md)

Reload skhd:

```bash
skhd --reload
```

### Notifications

The `install-hotkeys` command automatically installs terminal-notifier for visual feedback.

Configure notifications in System Settings:
1. Settings → Notifications → terminal-notifier
2. Enable "Allow Notifications"
3. Set Alert style to **Persistent** for recording indicators

## Linux Setup

### Hyprland

Add to `~/.config/hypr/hyprland.conf`:

```bash
# Transcribe to clipboard
bind = SUPER SHIFT, R, exec, agent-cli transcribe --toggle --input-device-index 1

# Autocorrect clipboard
bind = SUPER SHIFT, A, exec, agent-cli autocorrect

# Voice edit clipboard
bind = SUPER SHIFT, V, exec, agent-cli voice-edit --toggle --input-device-index 1

# Speak clipboard
bind = SUPER SHIFT, S, exec, agent-cli speak
```

### i3/Sway

Add to `~/.config/i3/config` or `~/.config/sway/config`:

```bash
# Transcribe to clipboard
bindsym $mod+Shift+r exec agent-cli transcribe --toggle --input-device-index 1

# Autocorrect clipboard
bindsym $mod+Shift+a exec agent-cli autocorrect

# Voice edit clipboard
bindsym $mod+Shift+v exec agent-cli voice-edit --toggle --input-device-index 1
```

### GNOME

Use `gsettings` or GNOME Settings → Keyboard → Custom Shortcuts:

```bash
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
  "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']"

gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ \
  name 'Transcribe'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ \
  command 'agent-cli transcribe --toggle --input-device-index 1'
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/ \
  binding '<Super><Shift>r'
```

### KDE Plasma

1. System Settings → Shortcuts → Custom Shortcuts
2. Edit → New → Global Shortcut → Command/URL
3. Set trigger (e.g., Super+Shift+R)
4. Set command: `agent-cli transcribe --toggle --input-device-index 1`

## Windows Setup (WSL2)

### AutoHotkey

Install [AutoHotkey](https://www.autohotkey.com/) and create a script:

```ahk
; Transcribe to clipboard
#+r::Run, agent-cli transcribe --toggle --input-device-index 1

; Autocorrect clipboard
#+a::Run, agent-cli autocorrect
```

### PowerToys

Use PowerToys Run or Keyboard Manager to create custom shortcuts.

## iOS Setup

Use iOS Shortcuts to trigger Agent CLI transcription from your iPhone by connecting to a running Agent CLI server on your local network.

See the [iOS Shortcut Guide](iOS_Shortcut_Guide.md) for step-by-step setup instructions.

## NixOS Setup

See the [NixOS installation guide](installation/nixos.md) for declarative hotkey configuration.

## Recommended Hotkey Layout

| Hotkey | Command | Description |
|--------|---------|-------------|
| `Cmd/Super + Shift + R` | [`transcribe --toggle`](commands/transcribe.md) | Record voice → clipboard |
| `Cmd/Super + Shift + A` | [`autocorrect`](commands/autocorrect.md) | Fix clipboard text |
| `Cmd/Super + Shift + V` | [`voice-edit --toggle`](commands/voice-edit.md) | Edit clipboard with voice |
| `Cmd/Super + Shift + S` | [`speak`](commands/speak.md) | Read clipboard aloud |

## Finding Your Audio Device

Before setting up hotkeys, find your microphone's device index:

```bash
agent-cli transcribe --list-devices
```

Look for your microphone and note its index number.

## Workflow Tips

### Typical Voice-to-LLM Workflow

1. **Copy context** (email, code, document)
2. **Press transcribe hotkey** → start speaking
3. **Press hotkey again** → text copied to clipboard
4. **Paste** into your LLM chat

### Voice Editing Workflow

1. **Copy draft text**
2. **Press voice-edit hotkey** → "make this more formal"
3. **Press hotkey again** → edited text in clipboard
4. **Paste** the improved version

### Autocorrect Workflow

1. **Type quickly** (with typos)
2. **Select and copy**
3. **Press autocorrect hotkey**
4. **Paste** corrected text

## Troubleshooting

### Hotkey Not Working

```bash
# Check if agent-cli is in PATH
which agent-cli

# Test command directly
agent-cli transcribe --list-devices

# Check hotkey daemon is running (macOS)
brew services list | grep skhd
```

### Audio Device Issues

```bash
# List devices
agent-cli transcribe --list-devices

# Test with specific device
agent-cli transcribe --input-device-index 1
```

### Permission Issues (macOS)

1. System Settings → Privacy & Security → Microphone
2. Add your terminal app (Terminal, iTerm2, Alacritty, etc.)
3. Restart the terminal
