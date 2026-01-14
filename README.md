# Agent CLI

<img src="https://raw.githubusercontent.com/basnijholt/agent-cli/refs/heads/main/.github/logo.svg" alt="agent-cli logo" align="right" style="width: 250px;" />

`agent-cli` is a collection of **_local-first_**, AI-powered command-line agents that run entirely on your machine.
It provides a suite of powerful tools for voice and text interaction, designed for privacy, offline capability, and seamless integration with system-wide hotkeys and workflows.

> [!TIP]
> **Short aliases available:** You can use `agent` or `ag` instead of `agent-cli` for convenience.

> [!IMPORTANT]
> **Local and Private by Design**
> All agents in this tool are designed to run **100% locally**.
> Your data, whether it's from your clipboard, microphone, or files, is never sent to any cloud API.
> This ensures your privacy and allows the tools to work completely offline.
> You can also optionally configure the agents to use OpenAI/Gemini services.

<!-- SECTION:why-i-built-this:START -->
## Why I built this

I got tired of typing long prompts to LLMs. Speaking is faster, so I built this tool to transcribe my voice directly to the clipboard with a hotkey.

**What it does:**

- Voice transcription to clipboard with system-wide hotkeys (Cmd+Shift+R on macOS)
- Autocorrect any text from your clipboard
- Edit clipboard content with voice commands ("make this more formal")
- Runs locally - no internet required, your audio stays on your machine
- Works with any app that can copy/paste

I use it mostly for the `transcribe` command when working with LLMs. Being able to speak naturally means I can provide more context without the typing fatigue.

Since then I have expanded the tool with many more features, all focused on local-first AI agents that integrate seamlessly with your system.
<!-- SECTION:why-i-built-this:END -->

[![A demo video of Agent-CLI showing local AI voice and text tools on a desktop.](http://img.youtube.com/vi/7sBTCgttH48/0.jpg)](http://www.youtube.com/watch?v=7sBTCgttH48 "Agent-CLI: Local AI Voice & Text Tools on Your Desktop (macOS Demo)")

*See agent-cli in action: [Watch the demo](https://www.youtube.com/watch?v=7sBTCgttH48)*

## Features

- **[`autocorrect`](docs/commands/autocorrect.md)**: Correct grammar and spelling in your text using a local LLM.
- **[`transcribe`](docs/commands/transcribe.md)**: Transcribe audio from your microphone to clipboard.
- **[`speak`](docs/commands/speak.md)**: Convert text to speech using a local TTS engine.
- **[`voice-edit`](docs/commands/voice-edit.md)**: Edit clipboard text with voice commands.
- **[`assistant`](docs/commands/assistant.md)**: Wake word-based voice assistant.
- **[`chat`](docs/commands/chat.md)**: Conversational AI with tool-calling capabilities.
- **[`memory`](docs/commands/memory.md)**: Long-term memory system with `memory proxy` and `memory add`.
- **[`rag-proxy`](docs/commands/rag-proxy.md)**: RAG proxy server for chatting with your documents.
- **[`dev`](docs/commands/dev.md)**: Parallel development with git worktrees and AI coding agents.
- **[`server`](docs/commands/server.md)**: HTTP API server for transcription.
- **[`transcribe-daemon`](docs/commands/transcribe-daemon.md)**: Continuous background transcription with VAD. Install with `uv tool install "agent-cli[vad]"`.

## Quick Start

### Just want the CLI tool?

If you already have AI services running (or plan to use OpenAI), simply install:

```bash
# Using uv (recommended)
uv tool install agent-cli

# Using pip
pip install agent-cli
```

Then use it:
```bash
agent-cli autocorrect "this has an eror"
```

### Want automatic setup with everything?

We offer two ways to set up agent-cli with all services:

#### Option A: Using Shell Scripts (Traditional)

```bash
# 1. Clone the repository
git clone https://github.com/basnijholt/agent-cli.git
cd agent-cli

# 2. Run setup (installs all services + agent-cli)
./scripts/setup-macos.sh  # or setup-linux.sh

# 3. Start services
./scripts/start-all-services.sh

# 4. (Optional) Set up system-wide hotkeys
./scripts/setup-macos-hotkeys.sh  # or setup-linux-hotkeys.sh

# 5. Use it!
agent-cli autocorrect "this has an eror"
```

#### Option B: Using CLI Commands (New!)

> [!NOTE]
> `agent-cli` uses `sounddevice` for real-time microphone/voice features.
> On Linux only, you need to install the system-level PortAudio library  (`sudo apt install portaudio19-dev` / your distro's equivalent on Linux) **before** you run `uv tool install agent-cli`.
> On Windows and macOS, this is handled automatically.

```bash
# 1. Install agent-cli
uv tool install agent-cli

# 2. Install all required services
agent-cli install-services

# 3. Start all services
agent-cli start-services

# 4. (Optional) Set up system-wide hotkeys
agent-cli install-hotkeys

# 5. Use it!
agent-cli autocorrect "this has an eror"
```

The setup scripts automatically install:
- ✅ Package managers (Homebrew/uv) if needed
- ✅ All AI services (Ollama, Whisper, TTS, etc.)
- ✅ The `agent-cli` tool
- ✅ System dependencies
- ✅ Hotkey managers (if using hotkey scripts)

<details><summary><b><u>[ToC]</u></b> 📚</summary>

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Installation](#installation)
  - [Option 1: CLI Tool Only](#option-1-cli-tool-only)
  - [Option 2: Automated Full Setup](#option-2-automated-full-setup)
    - [Step 1: Clone the Repository](#step-1-clone-the-repository)
    - [Step 2: Run the Setup Script](#step-2-run-the-setup-script)
    - [Step 3: Start All Services](#step-3-start-all-services)
    - [Step 4: Test Your Installation](#step-4-test-your-installation)
- [System Integration](#system-integration)
  - [macOS Hotkeys](#macos-hotkeys)
  - [Linux Hotkeys](#linux-hotkeys)
- [Prerequisites](#prerequisites)
  - [What You Need to Install Manually](#what-you-need-to-install-manually)
  - [What the Setup Scripts Install for You](#what-the-setup-scripts-install-for-you)
    - [Core Requirements (Auto-installed)](#core-requirements-auto-installed)
    - [AI Services (Auto-installed and configured)](#ai-services-auto-installed-and-configured)
    - [Alternative Cloud Services (Optional)](#alternative-cloud-services-optional)
    - [Alternative Local LLM Servers](#alternative-local-llm-servers)
- [Usage](#usage)
  - [Installation Commands](#installation-commands)
  - [Configuration](#configuration)
    - [Managing Configuration](#managing-configuration)
    - [Provider Defaults](#provider-defaults)
  - [`autocorrect`](#autocorrect)
  - [`transcribe`](#transcribe)
  - [`transcribe-daemon`](#transcribe-daemon)
  - [`speak`](#speak)
  - [`voice-edit`](#voice-edit)
  - [`assistant`](#assistant)
  - [`chat`](#chat)
  - [`rag-proxy`](#rag-proxy)
  - [`memory`](#memory)
    - [`memory proxy`](#memory-proxy)
    - [`memory add`](#memory-add)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Pre-commit Hooks](#pre-commit-hooks)
- [Contributing](#contributing)
- [License](#license)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

</details>


## Installation

### Option 1: CLI Tool Only

If you already have AI services set up or plan to use cloud services (OpenAI/Gemini):

```bash
# Using uv (recommended)
uv tool install agent-cli

# Using pip
pip install agent-cli
```

### Option 2: Automated Full Setup

For a complete local setup with all AI services:

#### Step 1: Clone the Repository

```bash
git clone https://github.com/basnijholt/agent-cli.git
cd agent-cli
```

#### Step 2: Run the Setup Script

| Platform | Setup Command | What It Does | Detailed Guide |
|----------|---------------|--------------|----------------|
| **🍎 macOS** | `./scripts/setup-macos.sh` | Installs Homebrew (if needed), uv, Ollama, all services, and agent-cli | [macOS Guide](docs/installation/macos.md) |
| **🐧 Linux** | `./scripts/setup-linux.sh` | Installs uv, Ollama, all services, and agent-cli | [Linux Guide](docs/installation/linux.md) |
| **❄️ NixOS** | See guide → | Special instructions for NixOS | [NixOS Guide](docs/installation/nixos.md) |
| **🐳 Docker** | See guide → | Container-based setup (slower) | [Docker Guide](docs/installation/docker.md) |

#### Step 3: Start All Services

```bash
./scripts/start-all-services.sh
```

This launches all AI services in a single terminal session using Zellij.

#### Step 4: Test Your Installation

```bash
agent-cli autocorrect "this has an eror"
# Output: this has an error
```

> [!NOTE]
> The setup scripts handle everything automatically. For platform-specific details or troubleshooting, see the [installation guides](docs/installation/).

<details><summary><b>Development Installation</b></summary>

For contributing or development:

```bash
git clone https://github.com/basnijholt/agent-cli.git
cd agent-cli
uv sync
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

</details>

## System Integration

Want system-wide hotkeys? You'll need the repository for the setup scripts:

```bash
# If you haven't already cloned it
git clone https://github.com/basnijholt/agent-cli.git
cd agent-cli
```

### macOS Hotkeys

```bash
./scripts/setup-macos-hotkeys.sh
```

This script automatically:
- ✅ Installs Homebrew if not present
- ✅ Installs skhd (hotkey daemon) and terminal-notifier
- ✅ Configures these system-wide hotkeys:
  - **`Cmd+Shift+R`** - Toggle voice transcription
  - **`Cmd+Shift+A`** - Autocorrect clipboard text
  - **`Cmd+Shift+V`** - Voice edit clipboard text

> [!NOTE]
> After setup, you may need to grant Accessibility permissions to skhd in System Settings → Privacy & Security → Accessibility

> [!TIP]
> To keep the “Listening…” indicator visible for the whole recording, open System Settings → Notifications → *terminal-notifier* and set the Alert style to **Persistent** (or choose **Alerts** on older macOS versions).
> Also enable "Allow notification when mirroring or sharing the display".
> The hotkey scripts keep only the recording notification pinned; status and result toasts auto-dismiss.

### Linux Hotkeys

```bash
./scripts/setup-linux-hotkeys.sh
```

This script automatically:
- ✅ Installs notification tools if needed
- ✅ Provides configuration for your desktop environment
- ✅ Sets up these hotkeys:
  - **`Super+Shift+R`** - Toggle voice transcription
  - **`Super+Shift+A`** - Autocorrect clipboard text
  - **`Super+Shift+V`** - Voice edit clipboard text

The script supports Hyprland, GNOME, KDE, Sway, i3, XFCE, and provides instructions for manual configuration on other environments.


## Prerequisites

### What You Need to Install Manually

The only thing you need to have installed is **Git** to clone this repository. Everything else is handled automatically!

### What the Setup Scripts Install for You

Our installation scripts automatically handle all dependencies:

#### Core Requirements (Auto-installed)
- 🍺 **Homebrew** (macOS) - Installed if not present
- 🐍 **uv** - Python package manager - Installed automatically
- 📋 **Clipboard Tools** - Pre-installed on macOS, handled on Linux

#### AI Services (Auto-installed and configured)

| Service | Purpose | Auto-installed? |
|---------|---------|-----------------|
| **[Ollama](https://ollama.ai/)** | Local LLM for text processing | ✅ Yes, with default model |
| **[Wyoming Faster Whisper](https://github.com/rhasspy/wyoming-faster-whisper)** | Speech-to-text | ✅ Yes, via `uvx` |
| **[Wyoming Piper](https://github.com/rhasspy/wyoming-piper)** | Text-to-speech | ✅ Yes, via `uvx` |
| **[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)** | Premium TTS (optional) | ⚙️ Can be added later |
| **[Wyoming openWakeWord](https://github.com/rhasspy/wyoming-openwakeword)** | Wake word detection | ✅ Yes, for `assistant` |

#### Alternative Cloud Services (Optional)

If you prefer cloud services over local ones:

| Service | Purpose | Setup Required |
|---------|---------|----------------|
| **OpenAI** | LLM, Speech-to-text, TTS | API key in config |
| **Gemini** | LLM alternative | API key in config |

#### Alternative Local LLM Servers

You can also use other OpenAI-compatible local servers:

| Server | Purpose | Setup Required |
|---------|---------|----------------|
| **llama.cpp** | Local LLM inference | Use `--openai-base-url http://localhost:8080/v1` |
| **vLLM** | High-performance LLM serving | Use `--openai-base-url` with server endpoint |
| **Ollama** | Default local LLM | Already configured as default |

## Usage

This package provides multiple command-line tools, each designed for a specific purpose.

### Installation Commands

These commands help you set up `agent-cli` and its required services:

- **`install-services`**: Install all required AI services (Ollama, Whisper, Piper, OpenWakeWord)
- **`install-hotkeys`**: Set up system-wide hotkeys for quick access to agent-cli features
- **`start-services`**: Start all services in a Zellij terminal session

All necessary scripts are bundled with the package, so you can run these commands immediately after installing `agent-cli`.

### Configuration

All `agent-cli` commands can be configured using a TOML file. The configuration file is searched for in the following locations, in order:

1.  `./agent-cli-config.toml` (in the current directory)
2.  `~/.config/agent-cli/config.toml`

You can also specify a path to a configuration file using the `--config` option, e.g., `agent-cli transcribe --config /path/to/your/config.toml`.

Command-line options always take precedence over settings in the configuration file.

#### Managing Configuration

Use the `config` command to manage your configuration files:

```bash
# Create a new config file with all options (commented out as a template)
agent-cli config init

# View your current config (syntax highlighted)
agent-cli config show

# View config as raw text (for copy-paste)
agent-cli config show --raw

# Open config in your editor ($EDITOR, or nano/vim)
agent-cli config edit
```

<details>
<summary>See the output of <code>agent-cli config --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli config --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli config [OPTIONS] COMMAND [ARGS]...

 Manage agent-cli configuration files.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ init   Create a new config file with all options commented out.              │
│ edit   Open the config file in your default editor.                          │
│ show   Display the config file location and contents.                        │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

An example configuration file is also provided in [`example.agent-cli-config.toml`](./example.agent-cli-config.toml).

#### Provider Defaults

You can choose local or cloud services per capability by setting provider keys in
the `[defaults]` section of your configuration file.

```toml
[defaults]
# llm_provider = "ollama"  # 'ollama', 'openai', or 'gemini'
# asr_provider = "wyoming" # 'wyoming' or 'openai'
# tts_provider = "wyoming" # 'wyoming', 'openai', or 'kokoro'
# openai_api_key = "sk-..."
# gemini_api_key = "..."
```

### `autocorrect`

**Purpose:** Quickly fix spelling and grammar in any text you've copied.

**Workflow:** This is a simple, one-shot command.

1.  It reads text from your system clipboard (or from a direct argument).
2.  It sends the text to a local Ollama LLM with a prompt to perform only technical corrections.
3.  The corrected text is copied back to your clipboard, replacing the original.

**How to Use It:** This tool is ideal for integrating with a system-wide hotkey.

- **From Clipboard**: `agent-cli autocorrect`
- **From Argument**: `agent-cli autocorrect "this text has an eror"`

<details>
<summary>See the output of <code>agent-cli autocorrect --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli autocorrect --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli autocorrect [OPTIONS] [TEXT]

 Correct text from clipboard using a local or remote LLM.

╭─ General Options ────────────────────────────────────────────────────────────╮
│   text      [TEXT]  The text to correct. If not provided, reads from         │
│                     clipboard.                                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --log-level           TEXT  Set logging level.                               │
│                             [default: WARNING]                               │
│ --log-file            TEXT  Path to a file to write logs to.                 │
│ --quiet       -q            Suppress console output from rich.               │
│ --config              TEXT  Path to a TOML configuration file.               │
│ --print-args                Print the command line arguments, including      │
│                             variables taken from the configuration file.     │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `transcribe`

**Purpose:** A simple tool to turn your speech into text.

**Workflow:** This agent listens to your microphone and converts your speech to text in real-time.

1.  Run the command. It will start listening immediately.
2.  Speak into your microphone.
3.  Press `Ctrl+C` to stop recording.
4.  The transcribed text is copied to your clipboard.
5.  Optionally, use the `--llm` flag to have an Ollama model clean up the raw transcript (fixing punctuation, etc.).

**How to Use It:**

- **Simple Transcription**: `agent-cli transcribe --input-device-index 1`
- **With LLM Cleanup**: `agent-cli transcribe --input-device-index 1 --llm`

<details>
<summary>See the output of <code>agent-cli transcribe --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli transcribe --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli transcribe [OPTIONS]

 Wyoming ASR Client for streaming microphone audio to a transcription server.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration ──────────────────────────────────────────────────────────╮
│ --extra-instructions                TEXT  Additional instructions for the    │
│                                           LLM to process the transcription.  │
│ --llm                   --no-llm          Use an LLM to process the          │
│                                           transcript.                        │
│                                           [default: no-llm]                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Recovery ─────────────────────────────────────────────────────────────╮
│ --from-file                                PATH     Transcribe audio from a  │
│                                                     file (supports wav, mp3, │
│                                                     m4a, ogg, flac, aac,     │
│                                                     webm). Requires ffmpeg   │
│                                                     for non-WAV formats with │
│                                                     Wyoming provider.        │
│ --last-recording                           INTEGER  Transcribe a saved       │
│                                                     recording. Use 1 for     │
│                                                     most recent, 2 for       │
│                                                     second-to-last, etc. Use │
│                                                     0 to disable (default).  │
│                                                     [default: 0]             │
│ --save-recording    --no-save-recording             Save the audio recording │
│                                                     to disk for recovery.    │
│                                                     [default:                │
│                                                     save-recording]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('wyoming', 'openai',    │
│                             'gemini').                                       │
│                             [default: wyoming]                               │
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the audio input device to use. │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Wyoming ───────────────────────────────────────────────────────╮
│ --asr-wyoming-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --asr-wyoming-port        INTEGER  Wyoming ASR server port.                  │
│                                    [default: 10300]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: OpenAI-compatible ─────────────────────────────────────────────╮
│ --asr-openai-model           TEXT  The OpenAI model to use for ASR           │
│                                    (transcription).                          │
│                                    [default: whisper-1]                      │
│ --asr-openai-base-url        TEXT  Custom base URL for OpenAI-compatible ASR │
│                                    API (e.g., for custom Whisper server:     │
│                                    http://localhost:9898).                   │
│ --asr-openai-prompt          TEXT  Custom prompt to guide transcription      │
│                                    (optional).                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Gemini ────────────────────────────────────────────────────────╮
│ --asr-gemini-model        TEXT  The Gemini model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: gemini-3-flash-preview]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --clipboard              --no-clipboard          Copy result to clipboard.   │
│                                                  [default: clipboard]        │
│ --log-level                                TEXT  Set logging level.          │
│                                                  [default: WARNING]          │
│ --log-file                                 TEXT  Path to a file to write     │
│                                                  logs to.                    │
│ --quiet              -q                          Suppress console output     │
│                                                  from rich.                  │
│ --config                                   TEXT  Path to a TOML              │
│                                                  configuration file.         │
│ --print-args                                     Print the command line      │
│                                                  arguments, including        │
│                                                  variables taken from the    │
│                                                  configuration file.         │
│ --transcription-log                        PATH  Path to log transcription   │
│                                                  results with timestamps,    │
│                                                  hostname, model, and raw    │
│                                                  output.                     │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `transcribe-daemon`

**Purpose:** A continuous background transcription service that automatically detects and transcribes speech.

**Workflow:** Runs as a daemon, listening to your microphone and automatically segmenting speech using voice activity detection (VAD).

1. Run the command. It starts listening immediately.
2. Speak naturally - the daemon detects when you start and stop speaking.
3. Each speech segment is automatically transcribed and logged.
4. Optionally, audio is saved as MP3 files for later reference.
5. Press `Ctrl+C` to stop the daemon.

**Installation:** Requires the `vad` extra:
```bash
uv tool install "agent-cli[vad]"
```

**How to Use It:**

- **Basic Daemon**: `agent-cli transcribe-daemon`
- **With Custom Role**: `agent-cli transcribe-daemon --role meeting`
- **With LLM Cleanup**: `agent-cli transcribe-daemon --llm`
- **Custom Silence Threshold**: `agent-cli transcribe-daemon --silence-threshold 1.5`

**Output Files:**

- **Transcription Log**: `~/.config/agent-cli/transcriptions.jsonl` (JSON Lines format)
- **Audio Files**: `~/.config/agent-cli/audio/YYYY/MM/DD/*.mp3`

<details>
<summary>See the output of <code>agent-cli transcribe-daemon --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli transcribe-daemon --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli transcribe-daemon [OPTIONS]

 Run a continuous transcription daemon with voice activity detection.

 This command runs indefinitely, capturing audio from your microphone,
 detecting speech segments using Silero VAD, transcribing them, and logging
 results with timestamps.

 Examples: # Basic daemon agent-cli transcribe-daemon


  # With role and custom silence threshold
  agent-cli transcribe-daemon --role meeting --silence-threshold 1.5

  # With LLM cleanup
  agent-cli transcribe-daemon --llm --role notes

  # Custom log file and audio directory
  agent-cli transcribe-daemon --transcription-log ~/meeting.jsonl --audio-dir
  ~/audio


╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --role               -r                     TEXT   Role name for logging     │
│                                                    (e.g., 'meeting',         │
│                                                    'notes', 'user').         │
│                                                    [default: user]           │
│ --silence-threshold  -s                     FLOAT  Seconds of silence to end │
│                                                    a speech segment.         │
│                                                    [default: 1.0]            │
│ --min-segment        -m                     FLOAT  Minimum speech duration   │
│                                                    in seconds to trigger a   │
│                                                    segment.                  │
│                                                    [default: 0.25]           │
│ --vad-threshold                             FLOAT  VAD speech detection      │
│                                                    threshold (0.0-1.0).      │
│                                                    Higher = more aggressive  │
│                                                    filtering.                │
│                                                    [default: 0.3]            │
│ --save-audio             --no-save-audio           Save audio segments as    │
│                                                    MP3 files.                │
│                                                    [default: save-audio]     │
│ --audio-dir                                 PATH   Directory for MP3 files.  │
│                                                    Default:                  │
│                                                    ~/.config/agent-cli/audio │
│ --transcription-log  -t                     PATH   JSON Lines log file path. │
│                                                    Default:                  │
│                                                    ~/.config/agent-cli/tran… │
│ --clipboard              --no-clipboard            Copy each transcription   │
│                                                    to clipboard.             │
│                                                    [default: no-clipboard]   │
│ --help               -h                            Show this message and     │
│                                                    exit.                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('wyoming', 'openai',    │
│                             'gemini').                                       │
│                             [default: wyoming]                               │
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the audio input device to use. │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Wyoming ───────────────────────────────────────────────────────╮
│ --asr-wyoming-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --asr-wyoming-port        INTEGER  Wyoming ASR server port.                  │
│                                    [default: 10300]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: OpenAI-compatible ─────────────────────────────────────────────╮
│ --asr-openai-model           TEXT  The OpenAI model to use for ASR           │
│                                    (transcription).                          │
│                                    [default: whisper-1]                      │
│ --asr-openai-base-url        TEXT  Custom base URL for OpenAI-compatible ASR │
│                                    API (e.g., for custom Whisper server:     │
│                                    http://localhost:9898).                   │
│ --asr-openai-prompt          TEXT  Custom prompt to guide transcription      │
│                                    (optional).                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Gemini ────────────────────────────────────────────────────────╮
│ --asr-gemini-model        TEXT  The Gemini model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: gemini-3-flash-preview]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration ──────────────────────────────────────────────────────────╮
│ --llm    --no-llm      Use an LLM to process the transcript.                 │
│                        [default: no-llm]                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --log-level           TEXT  Set logging level.                               │
│                             [default: WARNING]                               │
│ --log-file            TEXT  Path to a file to write logs to.                 │
│ --quiet       -q            Suppress console output from rich.               │
│ --config              TEXT  Path to a TOML configuration file.               │
│ --print-args                Print the command line arguments, including      │
│                             variables taken from the configuration file.     │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `speak`

**Purpose:** Reads any text out loud.

**Workflow:** A straightforward text-to-speech utility.

1.  It takes text from a command-line argument or your clipboard.
2.  It sends the text to a Wyoming TTS server (like Piper).
3.  The generated audio is played through your default speakers.

**How to Use It:**

- **Speak from Argument**: `agent-cli speak "Hello, world!"`
- **Speak from Clipboard**: `agent-cli speak`
- **Save to File**: `agent-cli speak "Hello" --save-file hello.wav`

<details>
<summary>See the output of <code>agent-cli speak --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli speak --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli speak [OPTIONS] [TEXT]

 Convert text to speech using Wyoming or OpenAI-compatible TTS server.

╭─ General Options ────────────────────────────────────────────────────────────╮
│   text      [TEXT]  Text to speak. Reads from clipboard if not provided.     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --tts-provider        TEXT  The TTS provider to use ('wyoming', 'openai',    │
│                             'kokoro', 'gemini').                             │
│                             [default: wyoming]                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output ───────────────────────────────────────────────────────────────╮
│ --output-device-index        INTEGER  Index of the audio output device to    │
│                                       use for TTS.                           │
│ --output-device-name         TEXT     Output device name keywords for        │
│                                       partial matching.                      │
│ --tts-speed                  FLOAT    Speech speed multiplier (1.0 = normal, │
│                                       2.0 = twice as fast, 0.5 = half        │
│                                       speed).                                │
│                                       [default: 1.0]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Wyoming ──────────────────────────────────────────────────────╮
│ --tts-wyoming-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --tts-wyoming-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --tts-wyoming-voice           TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│ --tts-wyoming-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│ --tts-wyoming-speaker         TEXT     Speaker name for Wyoming TTS voice.   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: OpenAI-compatible ────────────────────────────────────────────╮
│ --tts-openai-model           TEXT  The OpenAI model to use for TTS.          │
│                                    [default: tts-1]                          │
│ --tts-openai-voice           TEXT  The voice to use for OpenAI-compatible    │
│                                    TTS.                                      │
│                                    [default: alloy]                          │
│ --tts-openai-base-url        TEXT  Custom base URL for OpenAI-compatible TTS │
│                                    API (e.g., http://localhost:8000/v1 for a │
│                                    proxy).                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Kokoro ───────────────────────────────────────────────────────╮
│ --tts-kokoro-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --tts-kokoro-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --tts-kokoro-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Gemini ───────────────────────────────────────────────────────╮
│ --tts-gemini-model        TEXT  The Gemini model to use for TTS.             │
│                                 [default: gemini-2.5-flash-preview-tts]      │
│ --tts-gemini-voice        TEXT  The voice to use for Gemini TTS (e.g.,       │
│                                 'Kore', 'Puck', 'Charon', 'Fenrir').         │
│                                 [default: Kore]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --gemini-api-key        TEXT  Your Gemini API key. Can also be set with the  │
│                               GEMINI_API_KEY environment variable.           │
│                               [env var: GEMINI_API_KEY]                      │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --list-devices          List available audio input and output devices and    │
│                         exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file           PATH  Save TTS response audio to WAV file.             │
│ --log-level           TEXT  Set logging level.                               │
│                             [default: WARNING]                               │
│ --log-file            TEXT  Path to a file to write logs to.                 │
│ --quiet       -q            Suppress console output from rich.               │
│ --config              TEXT  Path to a TOML configuration file.               │
│ --print-args                Print the command line arguments, including      │
│                             variables taken from the configuration file.     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `voice-edit`

**Purpose:** A powerful clipboard assistant that you command with your voice.

**Workflow:** This agent is designed for a hotkey-driven workflow to act on text you've already copied.

1.  Copy a block of text to your clipboard (e.g., an email draft).
2.  Press a hotkey to run `agent-cli voice-edit &` in the background. The agent is now listening.
3.  Speak a command, such as "Make this more formal" or "Summarize the key points."
4.  Press the same hotkey again, which should trigger `agent-cli voice-edit --stop`.
5.  The agent transcribes your command, sends it along with the original clipboard text to the LLM, and the LLM performs the action.
6.  The result is copied back to your clipboard. If `--tts` is enabled, it will also speak the result.

**How to Use It:** The power of this tool is unlocked with a hotkey manager like Keyboard Maestro (macOS) or AutoHotkey (Windows). See the docstring in `agent_cli/agents/voice_edit.py` for a detailed Keyboard Maestro setup guide.

<details>
<summary>See the output of <code>agent-cli voice-edit --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli voice-edit --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli voice-edit [OPTIONS]

 Interact with clipboard text via a voice command using local or remote
 services.

 Usage:

  • Run in foreground: agent-cli voice-edit --input-device-index 1
  • Run in background: agent-cli voice-edit --input-device-index 1 &
  • Check status: agent-cli voice-edit --status
  • Stop background process: agent-cli voice-edit --stop
  • List output devices: agent-cli voice-edit --list-output-devices
  • Save TTS to file: agent-cli voice-edit --tts --save-file response.wav

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('wyoming', 'openai',    │
│                             'gemini').                                       │
│                             [default: wyoming]                               │
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
│ --tts-provider        TEXT  The TTS provider to use ('wyoming', 'openai',    │
│                             'kokoro', 'gemini').                             │
│                             [default: wyoming]                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the audio input device to use. │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Wyoming ───────────────────────────────────────────────────────╮
│ --asr-wyoming-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --asr-wyoming-port        INTEGER  Wyoming ASR server port.                  │
│                                    [default: 10300]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: OpenAI-compatible ─────────────────────────────────────────────╮
│ --asr-openai-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Gemini ────────────────────────────────────────────────────────╮
│ --asr-gemini-model        TEXT  The Gemini model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: gemini-3-flash-preview]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output ───────────────────────────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the audio output      │
│                                               device to use for TTS.         │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Wyoming ──────────────────────────────────────────────────────╮
│ --tts-wyoming-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --tts-wyoming-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --tts-wyoming-voice           TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│ --tts-wyoming-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│ --tts-wyoming-speaker         TEXT     Speaker name for Wyoming TTS voice.   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: OpenAI-compatible ────────────────────────────────────────────╮
│ --tts-openai-model           TEXT  The OpenAI model to use for TTS.          │
│                                    [default: tts-1]                          │
│ --tts-openai-voice           TEXT  The voice to use for OpenAI-compatible    │
│                                    TTS.                                      │
│                                    [default: alloy]                          │
│ --tts-openai-base-url        TEXT  Custom base URL for OpenAI-compatible TTS │
│                                    API (e.g., http://localhost:8000/v1 for a │
│                                    proxy).                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Kokoro ───────────────────────────────────────────────────────╮
│ --tts-kokoro-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --tts-kokoro-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --tts-kokoro-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Gemini ───────────────────────────────────────────────────────╮
│ --tts-gemini-model        TEXT  The Gemini model to use for TTS.             │
│                                 [default: gemini-2.5-flash-preview-tts]      │
│ --tts-gemini-voice        TEXT  The voice to use for Gemini TTS (e.g.,       │
│                                 'Kore', 'Puck', 'Charon', 'Fenrir').         │
│                                 [default: Kore]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file                         PATH  Save TTS response audio to WAV     │
│                                           file.                              │
│ --clipboard       --no-clipboard          Copy result to clipboard.          │
│                                           [default: clipboard]               │
│ --log-level                         TEXT  Set logging level.                 │
│                                           [default: WARNING]                 │
│ --log-file                          TEXT  Path to a file to write logs to.   │
│ --quiet       -q                          Suppress console output from rich. │
│ --config                            TEXT  Path to a TOML configuration file. │
│ --print-args                              Print the command line arguments,  │
│                                           including variables taken from the │
│                                           configuration file.                │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `assistant`

**Purpose:** A hands-free voice assistant that starts and stops recording based on a wake word.

**Workflow:** This agent continuously listens for a wake word (e.g., "Hey Nabu").

1.  Run the `assistant` command. It will start listening for the wake word.
2.  Say the wake word to start recording.
3.  Speak your command or question.
4.  Say the wake word again to stop recording.
5.  The agent transcribes your speech, sends it to the LLM, and gets a response.
6.  The agent speaks the response back to you and then immediately starts listening for the wake word again.

**How to Use It:**

- **Start the agent**: `agent-cli assistant --wake-word "ok_nabu" --input-device-index 1`
- **With TTS**: `agent-cli assistant --wake-word "ok_nabu" --tts --tts-wyoming-voice "en_US-lessac-medium"`

<details>
<summary>See the output of <code>agent-cli assistant --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli assistant --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli assistant [OPTIONS]

 Wake word-based voice assistant using local or remote services.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('wyoming', 'openai',    │
│                             'gemini').                                       │
│                             [default: wyoming]                               │
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
│ --tts-provider        TEXT  The TTS provider to use ('wyoming', 'openai',    │
│                             'kokoro', 'gemini').                             │
│                             [default: wyoming]                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Wake Word ──────────────────────────────────────────────────────────────────╮
│ --wake-server-ip          TEXT     Wyoming wake word server IP address.      │
│                                    [default: localhost]                      │
│ --wake-server-port        INTEGER  Wyoming wake word server port.            │
│                                    [default: 10400]                          │
│ --wake-word               TEXT     Name of wake word to detect (e.g.,        │
│                                    'ok_nabu', 'hey_jarvis').                 │
│                                    [default: ok_nabu]                        │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the audio input device to use. │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Wyoming ───────────────────────────────────────────────────────╮
│ --asr-wyoming-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --asr-wyoming-port        INTEGER  Wyoming ASR server port.                  │
│                                    [default: 10300]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: OpenAI-compatible ─────────────────────────────────────────────╮
│ --asr-openai-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Gemini ────────────────────────────────────────────────────────╮
│ --asr-gemini-model        TEXT  The Gemini model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: gemini-3-flash-preview]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output ───────────────────────────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the audio output      │
│                                               device to use for TTS.         │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Wyoming ──────────────────────────────────────────────────────╮
│ --tts-wyoming-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --tts-wyoming-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --tts-wyoming-voice           TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│ --tts-wyoming-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│ --tts-wyoming-speaker         TEXT     Speaker name for Wyoming TTS voice.   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: OpenAI-compatible ────────────────────────────────────────────╮
│ --tts-openai-model           TEXT  The OpenAI model to use for TTS.          │
│                                    [default: tts-1]                          │
│ --tts-openai-voice           TEXT  The voice to use for OpenAI-compatible    │
│                                    TTS.                                      │
│                                    [default: alloy]                          │
│ --tts-openai-base-url        TEXT  Custom base URL for OpenAI-compatible TTS │
│                                    API (e.g., http://localhost:8000/v1 for a │
│                                    proxy).                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Kokoro ───────────────────────────────────────────────────────╮
│ --tts-kokoro-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --tts-kokoro-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --tts-kokoro-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Gemini ───────────────────────────────────────────────────────╮
│ --tts-gemini-model        TEXT  The Gemini model to use for TTS.             │
│                                 [default: gemini-2.5-flash-preview-tts]      │
│ --tts-gemini-voice        TEXT  The voice to use for Gemini TTS (e.g.,       │
│                                 'Kore', 'Puck', 'Charon', 'Fenrir').         │
│                                 [default: Kore]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file                         PATH  Save TTS response audio to WAV     │
│                                           file.                              │
│ --clipboard       --no-clipboard          Copy result to clipboard.          │
│                                           [default: clipboard]               │
│ --log-level                         TEXT  Set logging level.                 │
│                                           [default: WARNING]                 │
│ --log-file                          TEXT  Path to a file to write logs to.   │
│ --quiet       -q                          Suppress console output from rich. │
│ --config                            TEXT  Path to a TOML configuration file. │
│ --print-args                              Print the command line arguments,  │
│                                           including variables taken from the │
│                                           configuration file.                │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `chat`

**Purpose:** A full-featured, conversational AI assistant that can interact with your system.

**Workflow:** This is a persistent, conversational agent that you can have a conversation with.

1.  Run the `chat` command. It will start listening for your voice.
2.  Speak your command or question (e.g., "What's in my current directory?").
3.  The agent transcribes your speech, sends it to the LLM, and gets a response. The LLM can use tools like `read_file` or `execute_code` to answer your question.
4.  The agent speaks the response back to you and then immediately starts listening for your next command.
5.  The conversation continues in this loop. Conversation history is saved between sessions.

**Interaction Model:**

- **To Interrupt**: Press `Ctrl+C` **once** to stop the agent from either listening or speaking, and it will immediately return to a listening state for a new command. This is useful if it misunderstands you or you want to speak again quickly.
- **To Exit**: Press `Ctrl+C` **twice in a row** to terminate the application.

**How to Use It:**

- **Start the agent**: `agent-cli chat --input-device-index 1 --tts`
- **Have a conversation**:
  - _You_: "Read the pyproject.toml file and tell me the project version."
  - _AI_: (Reads file) "The project version is 0.1.0."
  - _You_: "Thanks!"

<details>
<summary>See the output of <code>agent-cli chat --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli chat --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli chat [OPTIONS]

 An chat agent that you can talk to.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('wyoming', 'openai',    │
│                             'gemini').                                       │
│                             [default: wyoming]                               │
│ --llm-provider        TEXT  The LLM provider to use ('ollama', 'openai',     │
│                             'gemini').                                       │
│                             [default: ollama]                                │
│ --tts-provider        TEXT  The TTS provider to use ('wyoming', 'openai',    │
│                             'kokoro', 'gemini').                             │
│                             [default: wyoming]                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input ────────────────────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the audio input device to use. │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Wyoming ───────────────────────────────────────────────────────╮
│ --asr-wyoming-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --asr-wyoming-port        INTEGER  Wyoming ASR server port.                  │
│                                    [default: 10300]                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: OpenAI-compatible ─────────────────────────────────────────────╮
│ --asr-openai-model           TEXT  The OpenAI model to use for ASR           │
│                                    (transcription).                          │
│                                    [default: whisper-1]                      │
│ --asr-openai-base-url        TEXT  Custom base URL for OpenAI-compatible ASR │
│                                    API (e.g., for custom Whisper server:     │
│                                    http://localhost:9898).                   │
│ --asr-openai-prompt          TEXT  Custom prompt to guide transcription      │
│                                    (optional).                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Input: Gemini ────────────────────────────────────────────────────────╮
│ --asr-gemini-model        TEXT  The Gemini model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: gemini-3-flash-preview]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Ollama ────────────────────────────────────────────────────────────────╮
│ --llm-ollama-model        TEXT  The Ollama model to use. Default is          │
│                                 gemma3:4b.                                   │
│                                 [default: gemma3:4b]                         │
│ --llm-ollama-host         TEXT  The Ollama server host. Default is           │
│                                 http://localhost:11434.                      │
│                                 [default: http://localhost:11434]            │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --llm-openai-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-5-mini]                        │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│ --openai-base-url         TEXT  Custom base URL for OpenAI-compatible API    │
│                                 (e.g., for llama-server:                     │
│                                 http://localhost:8080/v1).                   │
│                                 [env var: OPENAI_BASE_URL]                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: Gemini ────────────────────────────────────────────────────────────────╮
│ --llm-gemini-model        TEXT  The Gemini model to use for LLM tasks.       │
│                                 [default: gemini-3-flash-preview]            │
│ --gemini-api-key          TEXT  Your Gemini API key. Can also be set with    │
│                                 the GEMINI_API_KEY environment variable.     │
│                                 [env var: GEMINI_API_KEY]                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output ───────────────────────────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the audio output      │
│                                               device to use for TTS.         │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Wyoming ──────────────────────────────────────────────────────╮
│ --tts-wyoming-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --tts-wyoming-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --tts-wyoming-voice           TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│ --tts-wyoming-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│ --tts-wyoming-speaker         TEXT     Speaker name for Wyoming TTS voice.   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: OpenAI-compatible ────────────────────────────────────────────╮
│ --tts-openai-model           TEXT  The OpenAI model to use for TTS.          │
│                                    [default: tts-1]                          │
│ --tts-openai-voice           TEXT  The voice to use for OpenAI-compatible    │
│                                    TTS.                                      │
│                                    [default: alloy]                          │
│ --tts-openai-base-url        TEXT  Custom base URL for OpenAI-compatible TTS │
│                                    API (e.g., http://localhost:8000/v1 for a │
│                                    proxy).                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Kokoro ───────────────────────────────────────────────────────╮
│ --tts-kokoro-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --tts-kokoro-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --tts-kokoro-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Audio Output: Gemini ───────────────────────────────────────────────────────╮
│ --tts-gemini-model        TEXT  The Gemini model to use for TTS.             │
│                                 [default: gemini-2.5-flash-preview-tts]      │
│ --tts-gemini-voice        TEXT  The voice to use for Gemini TTS (e.g.,       │
│                                 'Kore', 'Puck', 'Charon', 'Fenrir').         │
│                                 [default: Kore]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management ─────────────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ History Options ────────────────────────────────────────────────────────────╮
│ --history-dir            PATH     Directory to store conversation history.   │
│                                   [default: ~/.config/agent-cli/history]     │
│ --last-n-messages        INTEGER  Number of messages to include in the       │
│                                   conversation history. Set to 0 to disable  │
│                                   history.                                   │
│                                   [default: 50]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file           PATH  Save TTS response audio to WAV file.             │
│ --log-level           TEXT  Set logging level.                               │
│                             [default: WARNING]                               │
│ --log-file            TEXT  Path to a file to write logs to.                 │
│ --quiet       -q            Suppress console output from rich.               │
│ --config              TEXT  Path to a TOML configuration file.               │
│ --print-args                Print the command line arguments, including      │
│                             variables taken from the configuration file.     │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>


### `rag-proxy`

**Purpose:** Enables "Chat with your Data" by running a local proxy server that injects document context into LLM requests.

**Workflow:**

1.  Start the server, pointing it to your documents folder and your local LLM (e.g., Ollama or llama.cpp) or OpenAI.
2.  The server watches the folder and automatically indexes any text/markdown/PDF files into a local ChromaDB vector store.
3.  Point any OpenAI-compatible client (including `agent-cli chat`) to this server's URL.
4.  When you ask a question, the server retrieves relevant document chunks, adds them to the prompt, and forwards it to the LLM.

**How to Use It:**

- **Install RAG deps first**: `pip install "agent-cli[rag]"` (or, from the repo, `uv sync --extra rag`)
- **Start Server (Local LLM)**: `agent-cli rag-proxy --docs-folder ~/Documents/Notes --openai-base-url http://localhost:11434/v1 --port 8000`
- **Start Server (OpenAI)**: `agent-cli rag-proxy --docs-folder ~/Documents/Notes --openai-api-key sk-...`
- **Use with Agent-CLI**: `agent-cli chat --openai-base-url http://localhost:8000/v1 --llm-provider openai`

<details>
<summary>See the output of <code>agent-cli rag-proxy --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli rag-proxy --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli rag-proxy [OPTIONS]

 Start the RAG (Retrieval-Augmented Generation) Proxy Server.

 This server watches a folder for documents, indexes them, and provides an
 OpenAI-compatible API that proxies requests to a backend LLM (like llama.cpp),
 injecting relevant context from the documents.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ RAG Configuration ──────────────────────────────────────────────────────────╮
│ --docs-folder                      PATH     Folder to watch for documents    │
│                                             [default: ./rag_docs]            │
│ --chroma-path                      PATH     Path to ChromaDB persistence     │
│                                             directory                        │
│                                             [default: ./rag_db]              │
│ --limit                            INTEGER  Number of document chunks to     │
│                                             retrieve per query.              │
│                                             [default: 3]                     │
│ --rag-tools      --no-rag-tools             Allow agent to fetch full        │
│                                             documents when snippets are      │
│                                             insufficient.                    │
│                                             [default: rag-tools]             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --openai-base-url        TEXT  Custom base URL for OpenAI-compatible API     │
│                                (e.g., for llama-server:                      │
│                                http://localhost:8080/v1).                    │
│                                [env var: OPENAI_BASE_URL]                    │
│ --openai-api-key         TEXT  Your OpenAI API key. Can also be set with the │
│                                OPENAI_API_KEY environment variable.          │
│                                [env var: OPENAI_API_KEY]                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration ──────────────────────────────────────────────────────────╮
│ --embedding-model        TEXT  Embedding model to use for vectorization.     │
│                                [default: text-embedding-3-small]             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Server Configuration ───────────────────────────────────────────────────────╮
│ --host        TEXT     Host/IP to bind API servers to.                       │
│                        [default: 0.0.0.0]                                    │
│ --port        INTEGER  Port to bind to                                       │
│                        [default: 8000]                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --log-level         TEXT  Set logging level.                                 │
│                           [default: INFO]                                    │
│ --config            TEXT  Path to a TOML configuration file.                 │
│ --print-args              Print the command line arguments, including        │
│                           variables taken from the configuration file.       │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `memory`

The `memory proxy` command is the core feature—a middleware server that gives any OpenAI-compatible app long-term memory. Additional subcommands (`memory add`, etc.) help manage the memory store directly.

#### `memory proxy`

**Purpose:** Adds long-term conversational memory (self-hosted) to any OpenAI-compatible client.

**Key Features:**

- **Simple Markdown Files:** Your memories are stored as human-readable Markdown files, serving as the ultimate source of truth.
- **Automatic Version Control:** Built-in Git integration automatically commits changes, giving you a full history of your memory's evolution.
- **Lightweight & Local:** Minimal dependencies and runs entirely on your machine.
- **Proxy Middleware:** Works transparently with any OpenAI-compatible `/chat/completions` endpoint (OpenAI, Ollama, vLLM).

**Workflow:**

- Stores a per-conversation memory collection in Chroma with the same embedding settings as `rag-proxy`, reranked with a cross-encoder.
- For each turn, retrieves the top-k relevant memories (conversation + global) plus a rolling summary and augments the prompt.
- After each reply, extracts salient facts and refreshes the running summary (disable with `--no-summarization`).
- Enforces a per-conversation cap (`--max-entries`, default 500) and evicts oldest memories first.

**How to Use It:**

- **Install memory deps first**: `pip install "agent-cli[memory]"` (or, from the repo, `uv sync --extra memory`)
- **Start Server (Local LLM/OpenAI-compatible)**: `agent-cli memory proxy --memory-path ./memory_db --openai-base-url http://localhost:11434/v1 --embedding-model embeddinggemma:300m`
- **Use with Agent-CLI**: `agent-cli chat --openai-base-url http://localhost:8100/v1 --llm-provider openai`

<details>
<summary>See the output of <code>agent-cli memory proxy --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli memory proxy --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli memory proxy [OPTIONS]

 Start the memory-backed chat proxy server.

 This server acts as a middleware between your chat client (e.g., a web UI,
 CLI, or IDE plugin) and an OpenAI-compatible LLM provider (e.g., OpenAI,
 Ollama, vLLM).

 Key Features:

  • Simple Markdown Files: Memories are stored as human-readable Markdown
    files, serving as the ultimate source of truth.
  • Automatic Version Control: Built-in Git integration automatically commits
    changes, providing a full history of memory evolution.
  • Lightweight & Local: Minimal dependencies and runs entirely on your
    machine.
  • Proxy Middleware: Works transparently with any OpenAI-compatible
    /chat/completions endpoint.

 How it works:

  1 Intercepts POST /v1/chat/completions requests.
  2 Retrieves relevant memories (facts, previous conversations) from a local
    vector database (ChromaDB) based on the user's query.
  3 Injects these memories into the system prompt.
  4 Forwards the augmented request to the real LLM (--openai-base-url).
  5 Extracts new facts from the conversation in the background and updates the
    long-term memory store (including handling contradictions).

 Use this to give "long-term memory" to any OpenAI-compatible application.
 Point your client's base URL to http://localhost:8100/v1.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Memory Configuration ───────────────────────────────────────────────────────╮
│ --memory-path                               PATH     Path to the memory      │
│                                                      store (files + derived  │
│                                                      vector index).          │
│                                                      [default: ./memory_db]  │
│ --default-top-k                             INTEGER  Number of memory        │
│                                                      entries to retrieve per │
│                                                      query.                  │
│                                                      [default: 5]            │
│ --max-entries                               INTEGER  Maximum stored memory   │
│                                                      entries per             │
│                                                      conversation (excluding │
│                                                      summary).               │
│                                                      [default: 500]          │
│ --mmr-lambda                                FLOAT    MMR lambda (0-1):       │
│                                                      higher favors           │
│                                                      relevance, lower favors │
│                                                      diversity.              │
│                                                      [default: 0.7]          │
│ --recency-weight                            FLOAT    Recency score weight    │
│                                                      (0.0-1.0). Controls     │
│                                                      freshness vs.           │
│                                                      relevance. Default 0.2  │
│                                                      (20% recency, 80%       │
│                                                      semantic relevance).    │
│                                                      [default: 0.2]          │
│ --score-threshold                           FLOAT    Minimum semantic        │
│                                                      relevance threshold     │
│                                                      (0.0-1.0). Memories     │
│                                                      below this score are    │
│                                                      discarded to reduce     │
│                                                      noise.                  │
│                                                      [default: 0.35]         │
│ --summarization      --no-summarization              Enable automatic fact   │
│                                                      extraction and          │
│                                                      summaries.              │
│                                                      [default:               │
│                                                      summarization]          │
│ --git-versioning     --no-git-versioning             Enable automatic git    │
│                                                      commit of memory        │
│                                                      changes.                │
│                                                      [default:               │
│                                                      git-versioning]         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM: OpenAI-compatible ─────────────────────────────────────────────────────╮
│ --openai-base-url        TEXT  Custom base URL for OpenAI-compatible API     │
│                                (e.g., for llama-server:                      │
│                                http://localhost:8080/v1).                    │
│                                [env var: OPENAI_BASE_URL]                    │
│ --openai-api-key         TEXT  Your OpenAI API key. Can also be set with the │
│                                OPENAI_API_KEY environment variable.          │
│                                [env var: OPENAI_API_KEY]                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration ──────────────────────────────────────────────────────────╮
│ --embedding-model        TEXT  Embedding model to use for vectorization.     │
│                                [default: text-embedding-3-small]             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Server Configuration ───────────────────────────────────────────────────────╮
│ --host        TEXT     Host/IP to bind API servers to.                       │
│                        [default: 0.0.0.0]                                    │
│ --port        INTEGER  Port to bind to                                       │
│                        [default: 8100]                                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --log-level         TEXT  Set logging level.                                 │
│                           [default: INFO]                                    │
│ --config            TEXT  Path to a TOML configuration file.                 │
│ --print-args              Print the command line arguments, including        │
│                           variables taken from the configuration file.       │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

#### `memory add`

**Purpose:** Directly add memories to the store without LLM extraction. Useful for bulk imports or seeding memories.

**How to Use It:**

```bash
# Add single memories as arguments
agent-cli memory add "User likes coffee" "User lives in Amsterdam"

# Read from JSON file
agent-cli memory add -f memories.json

# Read from stdin (plain text, one per line)
echo "User prefers dark mode" | agent-cli memory add -f -

# Read JSON from stdin
echo '["Fact one", "Fact two"]' | agent-cli memory add -f -

# Specify conversation ID
agent-cli memory add -c work "Project deadline is Friday"
```

<details>
<summary>See the output of <code>agent-cli memory add --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export COLUMNS=90 -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli memory add --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli memory add [OPTIONS] [MEMORIES]...

 Add memories directly without LLM extraction.

 This writes facts directly to the memory store, bypassing the LLM-based fact
 extraction. Useful for bulk imports or seeding memories.

 The memory proxy file watcher (if running) will auto-index new files.
 Otherwise, they'll be indexed on next memory proxy startup.

 Examples::


  # Add single memories as arguments
  agent-cli memory add "User likes coffee" "User lives in Amsterdam"

  # Read from JSON file
  agent-cli memory add -f memories.json

  # Read from stdin (plain text, one per line)
  echo "User prefers dark mode" | agent-cli memory add -f -

  # Read JSON from stdin
  echo '["Fact one", "Fact two"]' | agent-cli memory add -f -

  # Specify conversation ID
  agent-cli memory add -c work "Project deadline is Friday"


╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│   memories      [MEMORIES]...  Memories to add. Each argument becomes one    │
│                                fact.                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --file             -f                         PATH  Read memories from file. │
│                                                     Use '-' for stdin.       │
│                                                     Supports JSON array,     │
│                                                     JSON object with         │
│                                                     'memories' key, or plain │
│                                                     text (one per line).     │
│ --conversation-id  -c                         TEXT  Conversation ID to add   │
│                                                     memories to.             │
│                                                     [default: default]       │
│ --memory-path                                 PATH  Path to the memory       │
│                                                     store.                   │
│                                                     [default: ./memory_db]   │
│ --git-versioning       --no-git-versioning          Commit changes to git.   │
│                                                     [default:                │
│                                                     git-versioning]          │
│ --help             -h                               Show this message and    │
│                                                     exit.                    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --quiet       -q            Suppress console output from rich.               │
│ --config              TEXT  Path to a TOML configuration file.               │
│ --print-args                Print the command line arguments, including      │
│                             variables taken from the configuration file.     │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

## Development

### Running Tests

The project uses `pytest` for testing. To run tests using `uv`:

```bash
uv run pytest
```

### Pre-commit Hooks

This project uses pre-commit hooks (ruff for linting and formatting, mypy for type checking) to maintain code quality. To set them up:

1. Install pre-commit:

   ```bash
   pip install pre-commit
   ```

2. Install the hooks:

   ```bash
   pre-commit install
   ```

   Now, the hooks will run automatically before each commit.

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue. If you'd like to contribute code, please fork the repository and submit a pull request.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
