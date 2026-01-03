---
icon: fontawesome/brands/windows
---

# Windows Installation Guide

`agent-cli` works natively on Windows - no WSL required! You can run all services (Ollama, Whisper, Piper) directly on Windows.

## Quick Start (Cloud Providers)

The fastest way to get started is using cloud providers:

```powershell
# Install uv (Python package manager)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install agent-cli
uv tool install agent-cli

# Use with cloud providers (requires API keys)
agent-cli transcribe --asr-provider openai --llm-provider openai
```

Set your API key as an environment variable:
```powershell
$env:OPENAI_API_KEY = "sk-..."
```

---

## Full Local Setup (No Cloud Required)

For a completely local setup with no internet dependency, install these services:

### 1. Install Ollama (LLM)

Download and install from [ollama.com](https://ollama.com/download/windows). Then pull a model:

```powershell
ollama pull llama3.2
```

Ollama runs automatically as a service on `localhost:11434`.

### 2. Install Whisper (Speech-to-Text)

Install the Wyoming Whisper server:

```powershell
# Create a virtual environment for the server
uv venv whisper-server
whisper-server\Scripts\activate

# Install wyoming-faster-whisper
uv pip install wyoming-faster-whisper

# Download a model and start the server
wyoming-faster-whisper --model small --uri tcp://0.0.0.0:10300 --data-dir ./whisper-data
```

> [!TIP]
> For GPU acceleration, ensure you have CUDA 12 and cuDNN 9 installed. See the [faster-whisper docs](https://github.com/SYSTRAN/faster-whisper#gpu) for details.

### 3. Install Piper (Text-to-Speech)

```powershell
# Create a virtual environment for the server
uv venv piper-server
piper-server\Scripts\activate

# Install wyoming-piper
uv pip install wyoming-piper

# Start the server (downloads voice automatically)
wyoming-piper --voice en_US-lessac-medium --uri tcp://0.0.0.0:10200 --data-dir ./piper-data
```

### 4. Install agent-cli

```powershell
uv tool install agent-cli
```

### 5. Test Your Setup

```powershell
# Test transcription (speak into your microphone)
agent-cli transcribe

# Test with specific providers
agent-cli transcribe --asr-provider wyoming --llm-provider ollama
```

> [!NOTE]
> If audio doesn't work, run `agent-cli transcribe --list-devices` to find your microphone's device index, then use `--input-device-index <number>`.

---

## Running Services at Startup

To run the Wyoming servers automatically, you can create Windows Task Scheduler entries or use a simple batch script:

```batch
@echo off
REM save as start-agent-services.bat

start "Whisper" cmd /k "whisper-server\Scripts\activate && wyoming-faster-whisper --model small --uri tcp://0.0.0.0:10300 --data-dir ./whisper-data"
start "Piper" cmd /k "piper-server\Scripts\activate && wyoming-piper --voice en_US-lessac-medium --uri tcp://0.0.0.0:10200 --data-dir ./piper-data"
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

2. Double-click the script to run it, or place it in your Startup folder.

> [!TIP]
> To run the script at startup, press `Win+R`, type `shell:startup`, and place a shortcut to your `.ahk` file there.

---

## Troubleshooting

### Audio device not found
Run `agent-cli transcribe --list-devices` and use the `--input-device-index` flag with your microphone's index.

### Wyoming server connection refused
Ensure the servers are running and listening on the correct ports:
- Whisper: `tcp://localhost:10300`
- Piper: `tcp://localhost:10200`

### GPU not being used for Whisper
Install CUDA 12 and cuDNN 9. You can verify GPU usage with:
```powershell
wyoming-faster-whisper --model small --uri tcp://0.0.0.0:10300 --device cuda
```

### Ollama not responding
Check that Ollama is running: `ollama list`. If not, start it from the Start Menu or run `ollama serve`.
