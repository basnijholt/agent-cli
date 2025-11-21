# Windows Installation Guide

While `agent-cli` does not have an automated setup script for native Windows, you can achieve a seamless experience by using a **Split Setup**.

This approach uses **WSL 2 (Windows Subsystem for Linux)** to run the heavy AI services (the "Brain") while running the lightweight `agent-cli` tool natively on Windows (the "Ears") to access your microphone and clipboard.

## Prerequisites

1.  **WSL 2**: Ensure you have WSL 2 installed (typically Ubuntu).
    *   [How to install WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
2.  **Git**: Installed in both WSL and Windows.
3.  **uv**: The Python package manager (installed on Windows).

---

## Part 1: The "Brain" (WSL Side)

We will run the backend services (Ollama, Whisper, Piper, etc.) inside WSL.

1.  **Open your WSL terminal** (e.g., Ubuntu).
2.  **Clone the repository and run the Linux setup:**

    ```bash
    git clone https://github.com/basnijholt/agent-cli.git
    cd agent-cli
    ./scripts/setup-linux.sh
    ```

3.  **Start the services:**

    ```bash
    ./scripts/start-all-services.sh
    ```

    This will launch a Zellij session with all services running. By default, WSL forwards these ports (11434, 10300, 10200, 10400) to your Windows `localhost`.

---

## Part 2: The "Ears" (Windows Side)

Now we install the client on Windows so it can access your hardware (microphone) and interact with your desktop (clipboard).

### 1. Install uv
If you haven't installed `uv` yet, run this in PowerShell:
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
`uv` will automatically manage the required Python version for the tool.

### 2. Install agent-cli
Run the following command to install the tool:

```powershell
uv tool install agent-cli
```

> [!NOTE]
> `agent-cli` uses **sounddevice** for audio, which automatically includes the necessary PortAudio binaries for Windows. You typically do not need to install any external drivers or libraries manually.

### 3. Test the Connection
Run a command in PowerShell to verify that Windows can talk to the WSL services:

```powershell
# This records audio on Windows -> sends to WSL -> copies text to Windows clipboard
agent-cli transcribe
```

---

## Part 3: Automation (AutoHotkey)

To invoke these commands globally (like the macOS/Linux hotkeys), use [AutoHotkey v1.1](https://www.autohotkey.com/).

1.  Create a file named `agent-cli.ahk`.
2.  Paste the following script:

```autohotkey
    ; Win+Ctrl+Alt+R to toggle transcription (custom, to avoid OS defaults)
    #^!r::
        Run, agent-cli transcribe --toggle --input-device-index 1, , Hide
    return

    ; Win+Shift+A to autocorrect clipboard
    #+a::
        Run, agent-cli autocorrect, , Hide
    return

    ; Win+Shift+V to voice edit selection
    #+v::
        ; First copy current selection to clipboard
        Send, ^c
        ClipWait, 1
        Run, agent-cli voice-edit --input-device-index 1, , Hide
    return
    ```
3.  Double-click the script to run it.

> [!TIP]
> Using `--toggle` stops an existing background recorder if it's already running, so you can press the same hotkey to start/stop the session without leaving a stray process behind.

If you use **AutoHotkey v2**, the script syntax is slightly different:

```autohotkey
; Win+Ctrl+Alt+R to toggle transcription (custom, to avoid OS defaults)
#^!r::{
    Run "agent-cli transcribe --toggle", , "Hide"
}

; Win+Shift+A to autocorrect clipboard
#+a::{
    Run "agent-cli autocorrect", , "Hide"
}

; Win+Shift+V to voice edit selection
#+v::{
    Send "^c"
    ClipWait(1)
    Run "agent-cli voice-edit", , "Hide"
}
```

**Note on Audio Devices:**
If `agent-cli` doesn't pick up your microphone, run `agent-cli transcribe --list-devices` to find the correct `--input-device-index`.
