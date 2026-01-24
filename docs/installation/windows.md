---
icon: fontawesome/brands/windows
---

# Windows Installation Guide

> [!WARNING]
> **Community Testing Needed!** This Windows setup has not been tested on real Windows hardware yet. The scripts are direct translations of the working Linux/macOS scripts.
>
> If you try this and it works (or doesn't), please [open an issue](https://github.com/basnijholt/agent-cli/issues) to let us know! Pull requests with improvements are very welcome.

`agent-cli` works natively on Windows - no WSL required! All services (Ollama, Whisper, Piper) run directly on Windows.

## Prerequisites

- Windows 10/11
- 8GB+ RAM (16GB+ recommended for GPU acceleration)
- 10GB free disk space

### For GPU Acceleration (Optional)

- NVIDIA GPU (GTX 1060+ or RTX series recommended)
- NVIDIA drivers installed
- CUDA 12 and cuDNN 9 (see [faster-whisper GPU docs](https://github.com/SYSTRAN/faster-whisper#gpu))

## Quick Start (Cloud Providers)

The fastest way to get started - no local services needed:

```powershell
# Install uv (Python package manager)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install agent-cli
uv tool install agent-cli -p 3.13

# Use with cloud providers (requires API keys)
$env:OPENAI_API_KEY = "sk-..."
agent-cli transcribe --asr-provider openai --llm-provider openai
```

---

## Full Local Setup (Recommended)

For a completely local setup with no internet dependency.

### Script-Based Installation (Recommended)

1. **Clone the repository:**

   ```powershell
   git clone https://github.com/basnijholt/agent-cli.git
   cd agent-cli
   ```

2. **Run the setup script:**

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
   ```

3. **Start all services:**

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/start-all-services-windows.ps1
   ```

4. **Test the setup:**

   ```powershell
   agent-cli transcribe
   ```

### Manual Installation

If you prefer manual setup:

1. **Install uv:**

   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Install Ollama:**

   Download from [ollama.com](https://ollama.com/download/windows) and install. Then:

   ```powershell
   ollama pull gemma3:4b
   ```

3. **Install agent-cli:**

   ```powershell
   uv tool install agent-cli -p 3.13
   ```

4. **Run services individually:**

   ```powershell
   # Terminal 1: Ollama (may already be running as a service)
   ollama serve

   # Terminal 2: Whisper
   powershell -ExecutionPolicy Bypass -File scripts/run-whisper-windows.ps1

   # Terminal 3: Piper
   powershell -ExecutionPolicy Bypass -File scripts/run-piper-windows.ps1
   ```

---

## Services Overview

| Service     | Port  | GPU Support | Description              |
| ----------- | ----- | ----------- | ------------------------ |
| **Ollama**  | 11434 | ✅ CUDA     | LLM inference            |
| **Whisper** | 10300 | ✅ CUDA     | Speech-to-text (ASR)     |
| **Piper**   | 10200 | N/A         | Text-to-speech (TTS)     |

## GPU Acceleration

The scripts automatically detect NVIDIA GPU and use:

- **With GPU (CUDA):** `large-v3` model for best accuracy
- **Without GPU:** `tiny` model for faster CPU inference

To verify GPU is being used:

```powershell
nvidia-smi
```

---

## Global Hotkeys with AutoHotkey

Use [AutoHotkey v2](https://www.autohotkey.com/) for global keyboard shortcuts.

1. Create a file named `agent-cli.ahk`:

```autohotkey
#Requires AutoHotkey v2.0
Persistent

; Win+Shift+W - Toggle transcription
#+w::{
    statusFile := A_Temp . "\agent-cli-status.txt"
    cmd := Format('{1} /C agent-cli transcribe --status > "{2}" 2>&1', A_ComSpec, statusFile)
    RunWait(cmd, , "Hide")
    status := FileRead(statusFile)
    if InStr(status, "not running") {
        TrayTip("Starting transcription...", "agent-cli", 1)
        Run("agent-cli transcribe --toggle", , "Hide")
    } else {
        TrayTip("Stopping transcription...", "agent-cli", 1)
        Run("agent-cli transcribe --toggle", , "Hide")
    }
}

; Win+Shift+A - Autocorrect clipboard
#+a::{
    TrayTip("Autocorrecting...", "agent-cli", 1)
    Run("agent-cli autocorrect", , "Hide")
}

; Win+Shift+E - Voice edit selection
#+e::{
    Send("^c")
    ClipWait(1)
    TrayTip("Voice editing...", "agent-cli", 1)
    Run("agent-cli voice-edit", , "Hide")
}
```

2. Double-click the script to run it.

> [!TIP]
> To run at startup: Press `Win+R`, type `shell:startup`, and place a shortcut to your `.ahk` file there.

---

## Troubleshooting

### Audio device not found

Run `agent-cli transcribe --list-devices` and use `--input-device-index` with your microphone's index.

### Wyoming server connection refused

Ensure the services are running:

```powershell
# Check if ports are in use
netstat -an | findstr "10300 10200 11434"
```

### GPU not being used

1. Verify NVIDIA drivers: `nvidia-smi`
2. Check CUDA installation
3. Set device explicitly: `$env:WHISPER_DEVICE = "cuda"`

### Ollama not responding

Check if Ollama is running:

```powershell
ollama list
```

If not, start it: `ollama serve` or launch from Start Menu.
