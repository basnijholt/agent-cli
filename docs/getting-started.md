---
icon: lucide/rocket
---

# Getting Started

This guide walks you through installing Agent CLI and setting up your first voice-powered workflow.

## Prerequisites

Before you begin, ensure you have:

- **[uv](https://docs.astral.sh/uv/)** (recommended) or Python 3.11+
- **A microphone** for voice features
- **Speakers** for text-to-speech features

## Installation

### Option 1: CLI Tool Only

If you already have AI services set up or plan to use cloud services (OpenAI/Gemini):

```bash
# Using uv (recommended)
uv tool install agent-cli -p 3.13

# Using pip
pip install agent-cli
```

> [!NOTE]
> The `-p 3.13` flag is required because some dependencies don't support Python 3.14 yet.
> See [uv issue #8206](https://github.com/astral-sh/uv/issues/8206) for details.

### Option 2: Full Local Setup

For a complete local setup with all AI services:

> [!TIP]
> **Have a GPU?** Skip the setup below and run your own Whisper server in one command:
> ```bash
> pip install "agent-cli[whisper]"
> agent-cli server whisper
> ```
> Apple Silicon MLX-only setup:
> ```bash
> pip install "agent-cli[whisper-mlx]"
> agent-cli server whisper --backend mlx
> ```
> See [Local Whisper Server](commands/server/whisper.md) for details.

=== "Using CLI Commands"

    ```bash
    # 1. Install agent-cli
    uv tool install agent-cli -p 3.13

    # 2. Install all required services
    agent-cli install-services

    # 3. Start all services
    agent-cli start-services

    # 4. (Optional) Set up system-wide hotkeys
    agent-cli install-hotkeys
    ```

    See: [`install-services`](commands/install-services.md) | [`start-services`](commands/start-services.md) | [`install-hotkeys`](commands/install-hotkeys.md)

=== "Using Shell Scripts"

    ```bash
    # 1. Clone the repository
    git clone https://github.com/basnijholt/agent-cli.git
    cd agent-cli

    # 2. Run setup
    ./scripts/setup-macos.sh  # or setup-linux.sh

    # 3. Start services
    ./scripts/start-all-services.sh

    # 4. (Optional) Set up hotkeys
    ./scripts/setup-macos-hotkeys.sh  # or setup-linux-hotkeys.sh
    ```

### Verify Installation

```bash
agent-cli --version
agent-cli --help
```

> [!TIP]
> **Short aliases:** You can also use `agent` or `ag` instead of `agent-cli`:
> ```bash
> ag --version
> agent transcribe --help
> ```

## Test Your Setup

### Test Autocorrect

```bash
agent-cli autocorrect "this has an eror"
# Output: this has an error
```

See: [`autocorrect`](commands/autocorrect.md)

### Test Transcription

```bash
# List available microphones
agent-cli transcribe --list-devices

# Start transcribing (press Ctrl+C to stop)
agent-cli transcribe --input-device-index 1
```

See: [`transcribe`](commands/transcribe.md)

### Test Text-to-Speech

```bash
agent-cli speak "Hello, world!"
```

See: [`speak`](commands/speak.md)

## Platform-Specific Guides

For detailed installation instructions, see the platform-specific guides:

| Platform | Guide | Notes |
|----------|-------|-------|
| :fontawesome-brands-apple: **macOS** | [macOS Setup](installation/macos.md) | Full Metal GPU acceleration |
| :fontawesome-brands-linux: **Linux** | [Linux Setup](installation/linux.md) | NVIDIA GPU support |
| :simple-nixos: **NixOS** | [NixOS Setup](installation/nixos.md) | Declarative configuration |
| :fontawesome-brands-windows: **Windows** | [Windows Setup](installation/windows.md) | WSL2 recommended |
| :fontawesome-brands-docker: **Docker** | [Docker Setup](installation/docker.md) | Cross-platform |

## First Workflow: Voice Transcription

Here's a typical workflow for using voice transcription:

1. **Copy some text** you want to respond to (e.g., an email)
2. **Press your hotkey** (Cmd+Shift+R on macOS) to start recording
3. **Speak your response** naturally
4. **Press the hotkey again** to stop recording
5. **Paste** the transcribed text wherever you need it

## What's Next?

- [Configuration](configuration.md) - Customize settings and defaults
- [Commands Reference](commands/index.md) - Explore all available commands
- [System Integration](system-integration.md) - Set up system-wide hotkeys
