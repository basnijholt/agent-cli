# Agent CLI

<img src="https://raw.githubusercontent.com/basnijholt/agent-cli/refs/heads/main/.github/logo.svg" alt="agent-cli logo" align="right" style="width: 250px;" />

`agent-cli` is a collection of **_local-first_**, AI-powered command-line agents that run entirely on your machine.
It provides a suite of powerful tools for voice and text interaction, designed for privacy, offline capability, and seamless integration with system-wide hotkeys and workflows.

> [!IMPORTANT]
> **Local and Private by Design**
> All agents in this tool are designed to run **100% locally**.
> Your data, whether it's from your clipboard, microphone, or files, is never sent to any cloud API.
> This ensures your privacy and allows the tools to work completely offline.
> You can also optionally configure the agents to use OpenAI/Gemini services.

## Why I built this

I got tired of typing long prompts to LLMs. Speaking is faster, so I built this tool to transcribe my voice directly to the clipboard with a hotkey.

What it does:
- Voice transcription to clipboard with system-wide hotkeys (Cmd+Shift+R on macOS)
- Autocorrect any text from your clipboard
- Edit clipboard content with voice commands ("make this more formal")
- Runs locally - no internet required, your audio stays on your machine
- Works with any app that can copy/paste

I use it mostly for the `transcribe` function when working with LLMs. Being able to speak naturally means I can provide more context without the typing fatigue.

[![A demo video of Agent-CLI showing local AI voice and text tools on a desktop.](http://img.youtube.com/vi/7sBTCgttH48/0.jpg)](http://www.youtube.com/watch?v=7sBTCgttH48 "Agent-CLI: Local AI Voice & Text Tools on Your Desktop (macOS Demo)")

*See agent-cli in action: [Watch the demo](https://www.youtube.com/watch?v=7sBTCgttH48)*

## Features

- **`autocorrect`**: Correct grammar and spelling in your text (e.g., from clipboard) using a local LLM with Ollama or OpenAI.
- **`transcribe`**: Transcribe audio from your microphone to text in your clipboard using a local Whisper model or OpenAI's Whisper API.
- **`speak`**: Convert text to speech using a local TTS engine or OpenAI's TTS API.
- **`voice-edit`**: A voice-powered clipboard assistant that edits text based on your spoken commands.
- **`assistant`**: A hands-free voice assistant that starts and stops recording based on a wake word.
- **`chat`**: A conversational AI agent with tool-calling capabilities.

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

Our scripts install and configure everything for you:

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
- [Usage](#usage)
  - [Configuration](#configuration)
    - [Service Provider](#service-provider)
  - [`autocorrect`](#autocorrect)
  - [`transcribe`](#transcribe)
  - [`speak`](#speak)
  - [`voice-edit`](#voice-edit)
  - [`assistant`](#assistant)
  - [`chat`](#chat)
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
- 🎶 **PortAudio** - For microphone and speaker I/O - Installed via package manager
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

## Usage

This package provides multiple command-line tools, each designed for a specific purpose.

### Configuration

All `agent-cli` commands can be configured using a TOML file. The configuration file is searched for in the following locations, in order:

1.  `./agent-cli-config.toml` (in the current directory)
2.  `~/.config/agent-cli/config.toml`

You can also specify a path to a configuration file using the `--config` option, e.g., `agent-cli transcribe --config /path/to/your/config.toml`.

Command-line options always take precedence over settings in the configuration file.

An example configuration file is provided in `example.agent-cli-config.toml`.

#### Service Provider

You can choose to use local services (Wyoming/Ollama) or OpenAI services by setting the `service_provider` option in the `[defaults]` section of your configuration file.

```toml
[defaults]
# service_provider = "openai"  # 'local' or 'openai'
# openai_api_key = "sk-..."
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli autocorrect --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli transcribe --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli speak --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli voice-edit --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
- **With TTS**: `agent-cli assistant --wake-word "ok_nabu" --tts --voice "en_US-lessac-medium"`

<details>
<summary>See the output of <code>agent-cli assistant --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli assistant --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli chat --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml
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
