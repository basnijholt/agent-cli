# Agent CLI

<img src="https://raw.githubusercontent.com/basnijholt/agent-cli/refs/heads/main/.github/logo.svg" alt="agent-cli logo" align="right" style="width: 250px;" />

`agent-cli` is a collection of **_local-first_**, AI-powered command-line agents that run entirely on your machine.
It provides a suite of powerful tools for voice and text interaction, designed for privacy, offline capability, and seamless integration with system-wide hotkeys and workflows.

> [!TIP]
> If using [`uv`](https://docs.astral.sh/uv/), you can easily run the tools from this package directly. For example, to see the help message for `autocorrect`:
>
> ```bash
> uvx agent-cli autocorrect --help
> ```

<details><summary><b><u>[ToC]</u></b> 📚</summary>

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Features](#features)
- [Prerequisites](#prerequisites)
  - [🧠 LLM (Large Language Model)](#-llm-large-language-model)
  - [🎤 ASR (Automatic Speech Recognition)](#-asr-automatic-speech-recognition)
  - [🗣️ TTS (Text-to-Speech)](#-tts-text-to-speech)
  - [👂 Wake Word](#-wake-word)
- [Installation](#installation)
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

> [!IMPORTANT]
> **Local and Private by Design**
> All agents in this toolkit are designed to run **100% locally**.
> Your data, whether it's from your clipboard, microphone, or files, is never sent to any cloud API.
> This ensures your privacy and allows the tools to work completely offline.
> You can also optionally configure the agents to use OpenAI services.

## Features

- **`autocorrect`**: Correct grammar and spelling in your text (e.g., from clipboard) using a local LLM with Ollama or OpenAI.
- **`transcribe`**: Transcribe audio from your microphone to text in your clipboard using a local Whisper model or OpenAI's Whisper API.
- **`speak`**: Convert text to speech using a local TTS engine or OpenAI's TTS API.
- **`voice-edit`**: A voice-powered clipboard assistant that edits text based on your spoken commands.
- **`assistant`**: A hands-free voice assistant that starts and stops recording based on a wake word.
- **`chat`**: A conversational AI agent with tool-calling capabilities.

## Prerequisites

To run `agent-cli`, you'll need the following core components:

- 🐍 **Python**: Version 3.11 or higher.
- 🎶 **PortAudio**: For microphone and speaker I/O.
- 📋 **Clipboard Tools**: `xsel`/`xclip` (Linux) or `pbcopy`/`pbpaste` (macOS).

For specific functionalities, you can set up the following optional services:

### 🧠 LLM (Large Language Model)

| Service                          | Notes                                                          |
| -------------------------------- | -------------------------------------------------------------- |
| [**Ollama**](https://ollama.ai/) | For `autocorrect`, `voice-edit`, and `chat` with local models. |
| **OpenAI**                       | If you prefer to use a cloud service, an API key is required.  |

### 🎤 ASR (Automatic Speech Recognition)

| Service                                                                         | Notes                                                                 |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| [**Wyoming Faster Whisper**](https://github.com/rhasspy/wyoming-faster-whisper) | For `transcribe`, `voice-edit`, and `chat` with local speech-to-text. |
| **OpenAI**                                                                      | If you prefer to use a cloud service, an API key is required.         |

### 🗣️ TTS (Text-to-Speech)

| Service                                                        | Notes                                                                                                                              |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| [**Kokoro-FastAPI**](https://github.com/remsky/Kokoro-FastAPI) | The best open-source TTS model available 🥇, providing natural-sounding voices. Recommended for `speak`, `voice-edit`, and `chat`. |
| [**Wyoming Piper**](https://github.com/rhasspy/wyoming-piper)  | An alternative for local text-to-speech.                                                                                           |
| **OpenAI**                                                     | If you prefer to use a cloud service, an API key is required.                                                                      |

### 👂 Wake Word

| Service                                                                     | Notes                      |
| --------------------------------------------------------------------------- | -------------------------- |
| [**Wyoming openWakeWord**](https://github.com/rhasspy/wyoming-openwakeword) | For the `assistant` agent. |

This might sound like a lot, but it's actually quite simple to set up.

<details>
<summary>See and example for NixOS</summary>

Taken from [basnijholt/dotfiles](https://github.com/basnijholt/dotfiles/blob/70903ef31ac65d99d31b4d7bfad053227f79fae5/configs/nixos/configuration.nix#L182-L221).

```nix
  # --- AI & Machine Learning ---
  services.ollama = {
    enable = true;
    acceleration = "cuda";
    host = "0.0.0.0";
    openFirewall = true;
    environmentVariables = {
      OLLAMA_KEEP_ALIVE = "1h";
    };
  };
  services.wyoming.faster-whisper = {
    servers.english = {
      enable = true;
      model = "large-v3";
      language = "en";
      device = "cuda";
      uri = "tcp://0.0.0.0:10300";
    };
  };
  services.wyoming.piper.servers.yoda = {
    enable = true;
    voice = "en-us-ryan-high";
    uri = "tcp://0.0.0.0:10200";
  };
  services.wyoming.openwakeword = {
    enable = true;
    preloadModels = [
      "alexa"
      "hey_jarvis"
      "ok_nabu"
    ];
    uri = "tcp://0.0.0.0:10400";
  };
```

</details>

<details>
<summary>See an example using Kokoro-FastAPI with Docker</summary>

You can use Docker to run the `kokoro-fastapi` service.

For CPU:

```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

For NVIDIA GPU:

```bash
docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest
```

The API will be available at `http://localhost:8880`.

</details>

<details>
<summary>See an example using Docker</summary>

You can use the provided `docker-compose.yml` to set up the required services.
This will start three services:

- `ollama`: A service for running local LLMs. It will automatically pull the `qwen3:4b` model.
- `piper`: A text-to-speech service.
- `whisper`: A speech-to-text service.

Run the following command to build and start the services:

```bash
docker compose -f examples/docker-compose.yml up --build
```

This command will build the `ollama` image from the `examples/Dockerfile` and start all the services in the background.

To check if everything is running correctly, you can view the logs of the services:

```bash
docker compose -f examples/docker-compose.yml logs
```

You should see logs from all three services, and the `ollama` logs should indicate that the `qwen3:4b` model has been pulled successfully.

To stop the services, run:

```bash
docker compose -f examples/docker-compose.yml down
```

> ⚠️ The `ollama` service can be memory-intensive. If you experience issues with the `autocorrect`, `voice-edit`, or `chat` agents, you may need to increase the memory allocated to Docker.
>
> **Note on GPU Acceleration**:
>
> - **Ollama**: On macOS, Docker does not support GPU acceleration. For significantly better performance, it is recommended to install Ollama natively by downloading it from the [official website](https://ollama.com/download) or by using Homebrew. This will allow Ollama to use the Metal GPU on Apple Silicon devices. On Linux, NVIDIA GPU acceleration is supported.
> - **Whisper**: The official `rhasspy/wyoming-whisper` Docker image does not currently support GPU acceleration.

</details>

## Installation

Install `agent-cli` using `uv`:

```bash
uv tools install agent-cli
```

or using `pip`:

```bash
pip install agent-cli
```

Or for development:

1. **Clone the repository:**

   ```bash
   git clone git@github.com:basnijholt/agent-cli.git
   cd agent-cli
   ```

2. **Install in development mode:**

   ```bash
   uv sync
   source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
   ```

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


 Usage: agent-cli autocorrect [OPTIONS] [TEXT]

 Correct text from clipboard using a local or remote LLM.


╭─ General Options ────────────────────────────────────────────────────────────╮
│   text      [TEXT]  The text to correct. If not provided, reads from         │
│                     clipboard.                                               │
│                     [default: None]                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --llm-provider        TEXT  The LLM provider to use ('local' for Ollama,     │
│                             'openai').                                       │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: Ollama (local) ──────────────────────────────────────────╮
│ --ollama-model        TEXT  The Ollama model to use. Default is qwen3:4b.    │
│                             [default: qwen3:4b]                              │
│ --ollama-host         TEXT  The Ollama server host. Default is               │
│                             http://localhost:11434.                          │
│                             [default: http://localhost:11434]                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --log-level          TEXT  Set logging level. [default: WARNING]             │
│ --log-file           TEXT  Path to a file to write logs to. [default: None]  │
│ --quiet      -q            Suppress console output from rich.                │
│ --config             TEXT  Path to a TOML configuration file.                │
│                            [default: None]                                   │
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
│ --extra-instructions        TEXT  Additional instructions for the LLM to     │
│                                   process the transcription.                 │
│                                   [default: None]                            │
│ --help                            Show this message and exit.                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('local' for Wyoming,    │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --llm-provider        TEXT  The LLM provider to use ('local' for Ollama,     │
│                             'openai').                                       │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration ──────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the PyAudio input device to    │
│                                      use.                                    │
│                                      [default: None]                         │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│                                      [default: None]                         │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: Wyoming (local) ─────────────────────────────────╮
│ --wyoming-asr-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --wyoming-asr-port        INTEGER  Wyoming ASR server port. [default: 10300] │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: OpenAI ──────────────────────────────────────────╮
│ --openai-asr-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: Ollama (local) ──────────────────────────────────────────╮
│ --ollama-model        TEXT  The Ollama model to use. Default is qwen3:4b.    │
│                             [default: qwen3:4b]                              │
│ --ollama-host         TEXT  The Ollama server host. Default is               │
│                             http://localhost:11434.                          │
│                             [default: http://localhost:11434]                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration ──────────────────────────────────────────────────────────╮
│ --llm    --no-llm      Use an LLM to process the transcript.                 │
│                        [default: no-llm]                                     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management Options ─────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --clipboard      --no-clipboard          Copy result to clipboard.           │
│                                          [default: clipboard]                │
│ --log-level                        TEXT  Set logging level.                  │
│                                          [default: WARNING]                  │
│ --log-file                         TEXT  Path to a file to write logs to.    │
│                                          [default: None]                     │
│ --quiet      -q                          Suppress console output from rich.  │
│ --config                           TEXT  Path to a TOML configuration file.  │
│                                          [default: None]                     │
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
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli speak --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml


 Usage: agent-cli speak [OPTIONS] [TEXT]

 Convert text to speech using Wyoming or OpenAI TTS server.


╭─ General Options ────────────────────────────────────────────────────────────╮
│   text      [TEXT]  Text to speak. Reads from clipboard if not provided.     │
│                     [default: None]                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --tts-provider        TEXT  The TTS provider to use ('local' for Wyoming,    │
│                             'openai', 'kokoro').                             │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration ─────────────────────────────────────────╮
│ --output-device-index        INTEGER  Index of the PyAudio output device to  │
│                                       use for TTS.                           │
│                                       [default: None]                        │
│ --output-device-name         TEXT     Output device name keywords for        │
│                                       partial matching.                      │
│                                       [default: None]                        │
│ --tts-speed                  FLOAT    Speech speed multiplier (1.0 = normal, │
│                                       2.0 = twice as fast, 0.5 = half        │
│                                       speed).                                │
│                                       [default: 1.0]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Wyoming (local) ────────────────────────╮
│ --wyoming-tts-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --wyoming-tts-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --wyoming-voice               TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│                                        [default: None]                       │
│ --wyoming-tts-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│                                        [default: None]                       │
│ --wyoming-speaker             TEXT     Speaker name for Wyoming TTS voice.   │
│                                        [default: None]                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: OpenAI ─────────────────────────────────╮
│ --openai-tts-model        TEXT  The OpenAI model to use for TTS.             │
│                                 [default: tts-1]                             │
│ --openai-tts-voice        TEXT  The voice to use for OpenAI TTS.             │
│                                 [default: alloy]                             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Kokoro ─────────────────────────────────╮
│ --kokoro-tts-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --kokoro-tts-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --kokoro-tts-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration ──────────────────────────────────────────────────╮
│ --list-devices          List available audio input and output devices and    │
│                         exit.                                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file          PATH  Save TTS response audio to WAV file.              │
│                            [default: None]                                   │
│ --log-level          TEXT  Set logging level. [default: WARNING]             │
│ --log-file           TEXT  Path to a file to write logs to. [default: None]  │
│ --quiet      -q            Suppress console output from rich.                │
│ --config             TEXT  Path to a TOML configuration file.                │
│                            [default: None]                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management Options ─────────────────────────────────────────────────╮
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

 Usage: - Run in foreground: agent-cli voice-edit --input-device-index 1 - Run
 in background: agent-cli voice-edit --input-device-index 1 & - Check status:
 agent-cli voice-edit --status - Stop background process: agent-cli voice-edit
 --stop - List output devices: agent-cli voice-edit --list-output-devices -
 Save TTS to file: agent-cli voice-edit --tts --save-file response.wav

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('local' for Wyoming,    │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --llm-provider        TEXT  The LLM provider to use ('local' for Ollama,     │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --tts-provider        TEXT  The TTS provider to use ('local' for Wyoming,    │
│                             'openai', 'kokoro').                             │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration ──────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the PyAudio input device to    │
│                                      use.                                    │
│                                      [default: None]                         │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│                                      [default: None]                         │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: Wyoming (local) ─────────────────────────────────╮
│ --wyoming-asr-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --wyoming-asr-port        INTEGER  Wyoming ASR server port. [default: 10300] │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: OpenAI ──────────────────────────────────────────╮
│ --openai-asr-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: Ollama (local) ──────────────────────────────────────────╮
│ --ollama-model        TEXT  The Ollama model to use. Default is qwen3:4b.    │
│                             [default: qwen3:4b]                              │
│ --ollama-host         TEXT  The Ollama server host. Default is               │
│                             http://localhost:11434.                          │
│                             [default: http://localhost:11434]                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration ─────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the PyAudio output    │
│                                               device to use for TTS.         │
│                                               [default: None]                │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│                                               [default: None]                │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Wyoming (local) ────────────────────────╮
│ --wyoming-tts-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --wyoming-tts-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --wyoming-voice               TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│                                        [default: None]                       │
│ --wyoming-tts-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│                                        [default: None]                       │
│ --wyoming-speaker             TEXT     Speaker name for Wyoming TTS voice.   │
│                                        [default: None]                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: OpenAI ─────────────────────────────────╮
│ --openai-tts-model        TEXT  The OpenAI model to use for TTS.             │
│                                 [default: tts-1]                             │
│ --openai-tts-voice        TEXT  The voice to use for OpenAI TTS.             │
│                                 [default: alloy]                             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Kokoro ─────────────────────────────────╮
│ --kokoro-tts-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --kokoro-tts-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --kokoro-tts-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management Options ─────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file                        PATH  Save TTS response audio to WAV      │
│                                          file.                               │
│                                          [default: None]                     │
│ --clipboard      --no-clipboard          Copy result to clipboard.           │
│                                          [default: clipboard]                │
│ --log-level                        TEXT  Set logging level.                  │
│                                          [default: WARNING]                  │
│ --log-file                         TEXT  Path to a file to write logs to.    │
│                                          [default: None]                     │
│ --quiet      -q                          Suppress console output from rich.  │
│ --config                           TEXT  Path to a TOML configuration file.  │
│                                          [default: None]                     │
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


 Usage: agent-cli assistant [OPTIONS]

 Wake word-based voice assistant using local or remote services.


╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('local' for Wyoming,    │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --llm-provider        TEXT  The LLM provider to use ('local' for Ollama,     │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --tts-provider        TEXT  The TTS provider to use ('local' for Wyoming,    │
│                             'openai', 'kokoro').                             │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Wake Word Options ──────────────────────────────────────────────────────────╮
│ --wake-server-ip          TEXT     Wyoming wake word server IP address.      │
│                                    [default: localhost]                      │
│ --wake-server-port        INTEGER  Wyoming wake word server port.            │
│                                    [default: 10400]                          │
│ --wake-word               TEXT     Name of wake word to detect (e.g.,        │
│                                    'ok_nabu', 'hey_jarvis').                 │
│                                    [default: ok_nabu]                        │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration ──────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the PyAudio input device to    │
│                                      use.                                    │
│                                      [default: None]                         │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│                                      [default: None]                         │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: Wyoming (local) ─────────────────────────────────╮
│ --wyoming-asr-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --wyoming-asr-port        INTEGER  Wyoming ASR server port. [default: 10300] │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: OpenAI ──────────────────────────────────────────╮
│ --openai-asr-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: Ollama (local) ──────────────────────────────────────────╮
│ --ollama-model        TEXT  The Ollama model to use. Default is qwen3:4b.    │
│                             [default: qwen3:4b]                              │
│ --ollama-host         TEXT  The Ollama server host. Default is               │
│                             http://localhost:11434.                          │
│                             [default: http://localhost:11434]                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration ─────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the PyAudio output    │
│                                               device to use for TTS.         │
│                                               [default: None]                │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│                                               [default: None]                │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Wyoming (local) ────────────────────────╮
│ --wyoming-tts-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --wyoming-tts-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --wyoming-voice               TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│                                        [default: None]                       │
│ --wyoming-tts-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│                                        [default: None]                       │
│ --wyoming-speaker             TEXT     Speaker name for Wyoming TTS voice.   │
│                                        [default: None]                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: OpenAI ─────────────────────────────────╮
│ --openai-tts-model        TEXT  The OpenAI model to use for TTS.             │
│                                 [default: tts-1]                             │
│ --openai-tts-voice        TEXT  The voice to use for OpenAI TTS.             │
│                                 [default: alloy]                             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Kokoro ─────────────────────────────────╮
│ --kokoro-tts-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --kokoro-tts-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --kokoro-tts-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management Options ─────────────────────────────────────────────────╮
│ --stop            Stop any running background process.                       │
│ --status          Check if a background process is running.                  │
│ --toggle          Toggle the background process on/off. If the process is    │
│                   running, it will be stopped. If the process is not         │
│                   running, it will be started.                               │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ General Options ────────────────────────────────────────────────────────────╮
│ --save-file                        PATH  Save TTS response audio to WAV      │
│                                          file.                               │
│                                          [default: None]                     │
│ --clipboard      --no-clipboard          Copy result to clipboard.           │
│                                          [default: clipboard]                │
│ --log-level                        TEXT  Set logging level.                  │
│                                          [default: WARNING]                  │
│ --log-file                         TEXT  Path to a file to write logs to.    │
│                                          [default: None]                     │
│ --quiet      -q                          Suppress console output from rich.  │
│ --config                           TEXT  Path to a TOML configuration file.  │
│                                          [default: None]                     │
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
│ --help          Show this message and exit.                                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Provider Selection ─────────────────────────────────────────────────────────╮
│ --asr-provider        TEXT  The ASR provider to use ('local' for Wyoming,    │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --llm-provider        TEXT  The LLM provider to use ('local' for Ollama,     │
│                             'openai').                                       │
│                             [default: local]                                 │
│ --tts-provider        TEXT  The TTS provider to use ('local' for Wyoming,    │
│                             'openai', 'kokoro').                             │
│                             [default: local]                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration ──────────────────────────────────────────────────╮
│ --input-device-index        INTEGER  Index of the PyAudio input device to    │
│                                      use.                                    │
│                                      [default: None]                         │
│ --input-device-name         TEXT     Device name keywords for partial        │
│                                      matching.                               │
│                                      [default: None]                         │
│ --list-devices                       List available audio input and output   │
│                                      devices and exit.                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: Wyoming (local) ─────────────────────────────────╮
│ --wyoming-asr-ip          TEXT     Wyoming ASR server IP address.            │
│                                    [default: localhost]                      │
│ --wyoming-asr-port        INTEGER  Wyoming ASR server port. [default: 10300] │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ ASR (Audio) Configuration: OpenAI ──────────────────────────────────────────╮
│ --openai-asr-model        TEXT  The OpenAI model to use for ASR              │
│                                 (transcription).                             │
│                                 [default: whisper-1]                         │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: Ollama (local) ──────────────────────────────────────────╮
│ --ollama-model        TEXT  The Ollama model to use. Default is qwen3:4b.    │
│                             [default: qwen3:4b]                              │
│ --ollama-host         TEXT  The Ollama server host. Default is               │
│                             http://localhost:11434.                          │
│                             [default: http://localhost:11434]                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ LLM Configuration: OpenAI ──────────────────────────────────────────────────╮
│ --openai-llm-model        TEXT  The OpenAI model to use for LLM tasks.       │
│                                 [default: gpt-4o-mini]                       │
│ --openai-api-key          TEXT  Your OpenAI API key. Can also be set with    │
│                                 the OPENAI_API_KEY environment variable.     │
│                                 [env var: OPENAI_API_KEY]                    │
│                                 [default: None]                              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration ─────────────────────────────────────────╮
│ --tts                    --no-tts             Enable text-to-speech for      │
│                                               responses.                     │
│                                               [default: no-tts]              │
│ --output-device-index                INTEGER  Index of the PyAudio output    │
│                                               device to use for TTS.         │
│                                               [default: None]                │
│ --output-device-name                 TEXT     Output device name keywords    │
│                                               for partial matching.          │
│                                               [default: None]                │
│ --tts-speed                          FLOAT    Speech speed multiplier (1.0 = │
│                                               normal, 2.0 = twice as fast,   │
│                                               0.5 = half speed).             │
│                                               [default: 1.0]                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Wyoming (local) ────────────────────────╮
│ --wyoming-tts-ip              TEXT     Wyoming TTS server IP address.        │
│                                        [default: localhost]                  │
│ --wyoming-tts-port            INTEGER  Wyoming TTS server port.              │
│                                        [default: 10200]                      │
│ --wyoming-voice               TEXT     Voice name to use for Wyoming TTS     │
│                                        (e.g., 'en_US-lessac-medium').        │
│                                        [default: None]                       │
│ --wyoming-tts-language        TEXT     Language for Wyoming TTS (e.g.,       │
│                                        'en_US').                             │
│                                        [default: None]                       │
│ --wyoming-speaker             TEXT     Speaker name for Wyoming TTS voice.   │
│                                        [default: None]                       │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: OpenAI ─────────────────────────────────╮
│ --openai-tts-model        TEXT  The OpenAI model to use for TTS.             │
│                                 [default: tts-1]                             │
│ --openai-tts-voice        TEXT  The voice to use for OpenAI TTS.             │
│                                 [default: alloy]                             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ TTS (Text-to-Speech) Configuration: Kokoro ─────────────────────────────────╮
│ --kokoro-tts-model        TEXT  The Kokoro model to use for TTS.             │
│                                 [default: kokoro]                            │
│ --kokoro-tts-voice        TEXT  The voice to use for Kokoro TTS.             │
│                                 [default: af_sky]                            │
│ --kokoro-tts-host         TEXT  The base URL for the Kokoro API.             │
│                                 [default: http://localhost:8880/v1]          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Process Management Options ─────────────────────────────────────────────────╮
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
│ --save-file          PATH  Save TTS response audio to WAV file.              │
│                            [default: None]                                   │
│ --log-level          TEXT  Set logging level. [default: WARNING]             │
│ --log-file           TEXT  Path to a file to write logs to. [default: None]  │
│ --quiet      -q            Suppress console output from rich.                │
│ --config             TEXT  Path to a TOML configuration file.                │
│                            [default: None]                                   │
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
