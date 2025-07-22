# macOS Transcription Toggle - Quick Start

## 🚀 One-Command Setup

```bash
./setup-macos-transcription.sh
```

That's it! The script handles everything automatically.

## 🎯 Usage

**Start Transcription:** Press `Cmd+Shift+R`
- 🎙️ Notification: "Transcription Started - Listening in background..."

**Stop Transcription:** Press `Cmd+Shift+R` again
- 🛑 Notification: "Transcription Stopped - Processing results..."

**Get Result:** Wait a moment
- 📄 Notification: Shows your transcribed text
- 📋 Clipboard: Text is automatically copied

## ⚡ What Gets Installed

- **skhd.zig**: Modern hotkey manager (replaces original skhd)
- **terminal-notifier**: Reliable macOS notifications
- **Configuration**: Automatic hotkey setup (Cmd+Shift+R)
- **Permissions**: Accessibility access for skhd

## 🔧 Prerequisites

Make sure you have agent-cli services running:

```bash
# Start required services
ollama serve &                    # LLM service
./run-whisper.sh &               # Speech-to-text service

# Or start all services at once
./start-all-services.sh
```

## 🎛️ Customization

**Change hotkey**: Edit `~/.config/skhd/skhdrc`
```bash
# Change Cmd+Shift+R to Cmd+Shift+T:
cmd + shift - t : /path/to/toggle-transcription-best.sh
```

**Additional shortcuts** (add to skhdrc):
```bash
# Auto-correct clipboard text
cmd + shift - a : ~/.local/bin/agent-cli autocorrect

# Speak clipboard text
cmd + shift - s : ~/.local/bin/agent-cli speak

# Start chat agent
cmd + shift - c : ~/.local/bin/agent-cli chat
```

## 🚨 Troubleshooting

**Hotkey not working?**
- Check skhd is running: `pgrep skhd`
- Grant accessibility permissions in System Settings
- Restart service: `skhd --restart-service`

**No notifications?**
- Test: `terminal-notifier -title "Test" -message "Hello"`
- Install if missing: `brew install terminal-notifier`

**Transcription fails?**
- Check services: `./start-all-services.sh`
- Verify agent-cli: `~/.local/bin/agent-cli --version`

## 🔍 Service Status Check

```bash
# Check if services are running
lsof -i :11434    # Ollama (should show process)
lsof -i :10300    # Wyoming ASR (should show process)
pgrep skhd        # skhd.zig (should show PID)
```

## 📚 Full Documentation

- **Complete Guide**: `README.md`
- **Manual Setup**: `INSTALL-MACOS-TOGGLE.md`
- **Alternatives**: `alternatives/` directory

---

**🎉 Ready to transcribe!** Press `Cmd+Shift+R` and start speaking!
