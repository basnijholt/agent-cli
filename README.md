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
- [Installation](#installation)
- [Usage](#usage)
  - [Configuration](#configuration)
  - [`autocorrect`](#autocorrect)
  - [`transcribe`](#transcribe)
  - [`speak`](#speak)
  - [`voice-assistant`](#voice-assistant)
  - [`wake-word-assistant`](#wake-word-assistant)
  - [`interactive`](#interactive)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Pre-commit Hooks](#pre-commit-hooks)
- [Contributing](#contributing)
- [License](#license)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

</details>

> [!IMPORTANT]
> **Local and Private by Design**
> All agents in this toolkit are designed to run **100% locally**. Your data, whether it's from your clipboard, microphone, or files, is never sent to any cloud API. This ensures your privacy and allows the tools to work completely offline.

## Features

- **`autocorrect`**: Correct grammar and spelling in your text (e.g., from clipboard) using a local LLM with Ollama.
- **`transcribe`**: Transcribe audio from your microphone to text in your clipboard.
- **`speak`**: Convert text to speech using a local TTS engine.
- **`voice-assistant`**: A voice-powered clipboard assistant that edits text based on your spoken commands.
- **`wake-word-assistant`**: A hands-free voice assistant that starts and stops recording based on a wake word.
- **`interactive`**: An interactive, conversational AI agent with tool-calling capabilities.

## Prerequisites

- **Python**: Version 3.11 or higher.
- **Ollama**: For `autocorrect`, `voice-assistant`, and `interactive`, you need [Ollama](https://ollama.ai/) running with a model pulled (e.g., `ollama pull mistral:latest`).
- **Wyoming Piper**: For `speak`, `voice-assistant`, and `interactive`, you need a [Wyoming TTS server](https://github.com/rhasspy/wyoming-piper) running for text-to-speech.
- **Wyoming Faster Whisper**: For `transcribe`, `voice-assistant`, and `interactive`, you need a [Wyoming ASR server](https://github.com/rhasspy/wyoming-faster-whisper) for speech-to-text.
- **Wyoming openWakeWord**: For `wake-word-assistant`, you need a [Wyoming wake word server](https://github.com/rhasspy/wyoming-openwakeword) running.
- **Clipboard Tools**: `xsel`, `xclip` (Linux), or `pbcopy`/`pbpaste` (macOS) are used by many agents.
- **PortAudio**: Required for PyAudio to handle microphone and speaker I/O.

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

> ⚠️ The `ollama` service can be memory-intensive. If you experience issues with the `autocorrect`, `voice-assistant`, or `interactive` agents, you may need to increase the memory allocated to Docker.

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

 Correct text from clipboard using a local Ollama model.


╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│   text      [TEXT]  The text to correct. If not provided, reads from         │
│                     clipboard.                                               │
│                     [default: None]                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --model           -m                TEXT  Name of the model to use.          │
│                                           [default: devstral:24b]            │
│ --ollama-host                       TEXT  Ollama server host.                │
│                                           [default: http://localhost:11434]  │
│ --llm-provider                      TEXT  LLM provider to use ("ollama" or   │
│                                           "openai").                         │
│                                           [default: ollama]                  │
│ --openai-api-key                    TEXT  OpenAI API key. [default: None]    │
│ --log-level                         TEXT  Set the log level (e.g., DEBUG,    │
│                                           INFO, WARNING).                    │
│                                           [default: INFO]                    │
│ --log-file                          TEXT  Path to a file to write logs to.   │
│                                           [default: None]                    │
│ --quiet               --no-quiet          Suppress all output except for the │
│                                           final result.                      │
│                                           [default: no-quiet]                │
│ --config-file                       TEXT  Path to a custom config file.      │
│                                           [default: None]                    │
│ --help                                    Show this message and exit.        │
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

 Usage: - Run in foreground: agent-cli transcribe --input-device-index 1 - Run
 in background: agent-cli transcribe --input-device-index 1 & - Check status:
 agent-cli transcribe --status - Stop background process: agent-cli transcribe
 --stop

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --input-device-index  -i                       INTEGER  Index of the input   │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --input-device-name   -I                       TEXT     Name of the input    │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Microphone').        │
│                                                         [default: None]      │
│ --asr-provider                                 TEXT     ASR provider to use  │
│                                                         ("wyoming" or        │
│                                                         "openai").           │
│                                                         [default: wyoming]   │
│ --asr-server-ip                                TEXT     IP address of the    │
│                                                         ASR server.          │
│                                                         [default: localhost] │
│ --asr-server-port                              INTEGER  Port of the ASR      │
│                                                         server.              │
│                                                         [default: 10300]     │
│ --openai-api-key                               TEXT     OpenAI API key.      │
│                                                         [default: None]      │
│ --whisper-model                                TEXT     Name of the Whisper  │
│                                                         model to use.        │
│                                                         [default: whisper-1] │
│ --model               -m                       TEXT     Name of the model to │
│                                                         use.                 │
│                                                         [default:            │
│                                                         devstral:24b]        │
│ --ollama-host                                  TEXT     Ollama server host.  │
│                                                         [default:            │
│                                                         http://localhost:11… │
│ --llm-provider                                 TEXT     LLM provider to use  │
│                                                         ("ollama" or         │
│                                                         "openai").           │
│                                                         [default: ollama]    │
│ --llm                     --no-llm                      Enable LLM           │
│                                                         processing of the    │
│                                                         transcript.          │
│                                                         [default: no-llm]    │
│ --stop                    --no-stop                     Stop the background  │
│                                                         process.             │
│                                                         [default: no-stop]   │
│ --status                  --no-status                   Check the status of  │
│                                                         the background       │
│                                                         process.             │
│                                                         [default: no-status] │
│ --toggle                  --no-toggle                   Toggle the           │
│                                                         background process   │
│                                                         on/off.              │
│                                                         [default: no-toggle] │
│ --clipboard               --no-clipboard                Copy the result to   │
│                                                         the clipboard.       │
│                                                         [default: clipboard] │
│ --log-level                                    TEXT     Set the log level    │
│                                                         (e.g., DEBUG, INFO,  │
│                                                         WARNING).            │
│                                                         [default: INFO]      │
│ --log-file                                     TEXT     Path to a file to    │
│                                                         write logs to.       │
│                                                         [default: None]      │
│ --list-devices            --no-list-devices             List available audio │
│                                                         devices and exit.    │
│                                                         [default:            │
│                                                         no-list-devices]     │
│ --quiet                   --no-quiet                    Suppress all output  │
│                                                         except for the final │
│                                                         result.              │
│                                                         [default: no-quiet]  │
│ --config-file                                  TEXT     Path to a custom     │
│                                                         config file.         │
│                                                         [default: None]      │
│ --help                                                  Show this message    │
│                                                         and exit.            │
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

 Convert text to speech using Wyoming TTS server.

 If no text is provided, reads from clipboard.
 Usage: - Speak text: agent-cli speak "Hello world" - Speak from clipboard:
 agent-cli speak - Save to file: agent-cli speak "Hello" --save-file hello.wav
 - Use specific voice: agent-cli speak "Hello" --voice en_US-lessac-medium -
 Run in background: agent-cli speak "Hello" &

╭─ Arguments ──────────────────────────────────────────────────────────────────╮
│   text      [TEXT]  Text to speak. Reads from clipboard if not provided.     │
│                     [default: None]                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --tts-server-ip                                TEXT     IP address of the    │
│                                                         TTS server.          │
│                                                         [default: localhost] │
│ --tts-server-port                              INTEGER  Port of the TTS      │
│                                                         server.              │
│                                                         [default: 10200]     │
│ --voice-name          -v                       TEXT     Name of the voice to │
│                                                         use for TTS.         │
│                                                         [default: None]      │
│ --tts-language                                 TEXT     Language to use for  │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --speaker                                      TEXT     Speaker to use for   │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --tts-speed                                    FLOAT    TTS speech speed.    │
│                                                         [default: 1.0]       │
│ --output-device-ind…  -o                       INTEGER  Index of the output  │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --output-device-name  -O                       TEXT     Name of the output   │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Speakers').          │
│                                                         [default: None]      │
│ --list-devices            --no-list-devices             List available audio │
│                                                         devices and exit.    │
│                                                         [default:            │
│                                                         no-list-devices]     │
│ --save-file                                    PATH     Save audio to WAV    │
│                                                         file instead of      │
│                                                         playing it.          │
│                                                         [default: None]      │
│ --stop                    --no-stop                     Stop the background  │
│                                                         process.             │
│                                                         [default: no-stop]   │
│ --status                  --no-status                   Check the status of  │
│                                                         the background       │
│                                                         process.             │
│                                                         [default: no-status] │
│ --toggle                  --no-toggle                   Toggle the           │
│                                                         background process   │
│                                                         on/off.              │
│                                                         [default: no-toggle] │
│ --log-level                                    TEXT     Set the log level    │
│                                                         (e.g., DEBUG, INFO,  │
│                                                         WARNING).            │
│                                                         [default: INFO]      │
│ --log-file                                     TEXT     Path to a file to    │
│                                                         write logs to.       │
│                                                         [default: None]      │
│ --quiet                   --no-quiet                    Suppress all output  │
│                                                         except for the final │
│                                                         result.              │
│                                                         [default: no-quiet]  │
│ --config-file                                  TEXT     Path to a custom     │
│                                                         config file.         │
│                                                         [default: None]      │
│ --help                                                  Show this message    │
│                                                         and exit.            │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `voice-assistant`

**Purpose:** A powerful clipboard assistant that you command with your voice.

**Workflow:** This agent is designed for a hotkey-driven workflow to act on text you've already copied.

1.  Copy a block of text to your clipboard (e.g., an email draft).
2.  Press a hotkey to run `agent-cli voice-assistant &` in the background. The agent is now listening.
3.  Speak a command, such as "Make this more formal" or "Summarize the key points."
4.  Press the same hotkey again, which should trigger `agent-cli voice-assistant --stop`.
5.  The agent transcribes your command, sends it along with the original clipboard text to the LLM, and the LLM performs the action.
6.  The result is copied back to your clipboard. If `--tts` is enabled, it will also speak the result.

**How to Use It:** The power of this tool is unlocked with a hotkey manager like Keyboard Maestro (macOS) or AutoHotkey (Windows). See the docstring in `agent_cli/agents/voice_assistant.py` for a detailed Keyboard Maestro setup guide.

<details>
<summary>See the output of <code>agent-cli voice-assistant --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli voice-assistant --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli voice-assistant [OPTIONS]

 Interact with clipboard text via a voice command using Wyoming and an Ollama
 LLM.

 Usage: - Run in foreground: agent-cli voice-assistant --input-device-index 1 -
 Run in background: agent-cli voice-assistant --input-device-index 1 & - Check
 status: agent-cli voice-assistant --status - Stop background process:
 agent-cli voice-assistant --stop - List output devices: agent-cli
 voice-assistant --list-output-devices - Save TTS to file: agent-cli
 voice-assistant --tts --save-file response.wav

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --input-device-index  -i                       INTEGER  Index of the input   │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --input-device-name   -I                       TEXT     Name of the input    │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Microphone').        │
│                                                         [default: None]      │
│ --asr-provider                                 TEXT     ASR provider to use  │
│                                                         ("wyoming" or        │
│                                                         "openai").           │
│                                                         [default: wyoming]   │
│ --asr-server-ip                                TEXT     IP address of the    │
│                                                         ASR server.          │
│                                                         [default: localhost] │
│ --asr-server-port                              INTEGER  Port of the ASR      │
│                                                         server.              │
│                                                         [default: 10300]     │
│ --whisper-model                                TEXT     Name of the Whisper  │
│                                                         model to use.        │
│                                                         [default: whisper-1] │
│ --model               -m                       TEXT     Name of the model to │
│                                                         use.                 │
│                                                         [default:            │
│                                                         devstral:24b]        │
│ --ollama-host                                  TEXT     Ollama server host.  │
│                                                         [default:            │
│                                                         http://localhost:11… │
│ --llm-provider                                 TEXT     LLM provider to use  │
│                                                         ("ollama" or         │
│                                                         "openai").           │
│                                                         [default: ollama]    │
│ --openai-api-key                               TEXT     OpenAI API key.      │
│                                                         [default: None]      │
│ --stop                    --no-stop                     Stop the background  │
│                                                         process.             │
│                                                         [default: no-stop]   │
│ --status                  --no-status                   Check the status of  │
│                                                         the background       │
│                                                         process.             │
│                                                         [default: no-status] │
│ --toggle                  --no-toggle                   Toggle the           │
│                                                         background process   │
│                                                         on/off.              │
│                                                         [default: no-toggle] │
│ --enable-tts              --no-enable-tts               Enable               │
│                                                         text-to-speech       │
│                                                         output.              │
│                                                         [default:            │
│                                                         no-enable-tts]       │
│ --tts-server-ip                                TEXT     IP address of the    │
│                                                         TTS server.          │
│                                                         [default: localhost] │
│ --tts-server-port                              INTEGER  Port of the TTS      │
│                                                         server.              │
│                                                         [default: 10200]     │
│ --voice-name          -v                       TEXT     Name of the voice to │
│                                                         use for TTS.         │
│                                                         [default: None]      │
│ --tts-language                                 TEXT     Language to use for  │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --speaker                                      TEXT     Speaker to use for   │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --tts-speed                                    FLOAT    TTS speech speed.    │
│                                                         [default: 1.0]       │
│ --output-device-ind…  -o                       INTEGER  Index of the output  │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --output-device-name  -O                       TEXT     Name of the output   │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Speakers').          │
│                                                         [default: None]      │
│ --save-file                                    PATH     Save audio to WAV    │
│                                                         file instead of      │
│                                                         playing it.          │
│                                                         [default: None]      │
│ --clipboard               --no-clipboard                Copy the result to   │
│                                                         the clipboard.       │
│                                                         [default: clipboard] │
│ --log-level                                    TEXT     Set the log level    │
│                                                         (e.g., DEBUG, INFO,  │
│                                                         WARNING).            │
│                                                         [default: INFO]      │
│ --log-file                                     TEXT     Path to a file to    │
│                                                         write logs to.       │
│                                                         [default: None]      │
│ --list-devices            --no-list-devices             List available audio │
│                                                         devices and exit.    │
│                                                         [default:            │
│                                                         no-list-devices]     │
│ --quiet                   --no-quiet                    Suppress all output  │
│                                                         except for the final │
│                                                         result.              │
│                                                         [default: no-quiet]  │
│ --config-file                                  TEXT     Path to a custom     │
│                                                         config file.         │
│                                                         [default: None]      │
│ --help                                                  Show this message    │
│                                                         and exit.            │
╰──────────────────────────────────────────────────────────────────────────────╯

```

<!-- OUTPUT:END -->

</details>

### `wake-word-assistant`

**Purpose:** A hands-free voice assistant that starts and stops recording based on a wake word.

**Workflow:** This agent continuously listens for a wake word (e.g., "Hey Nabu").

1.  Run the `wake-word-assistant` command. It will start listening for the wake word.
2.  Say the wake word to start recording.
3.  Speak your command or question.
4.  Say the wake word again to stop recording.
5.  The agent transcribes your speech, sends it to the LLM, and gets a response.
6.  The agent speaks the response back to you and then immediately starts listening for the wake word again.

**How to Use It:**

- **Start the agent**: `agent-cli wake-word-assistant --wake-word "ok_nabu" --input-device-index 1`
- **With TTS**: `agent-cli wake-word-assistant --wake-word "ok_nabu" --tts --voice "en_US-lessac-medium"`

<details>
<summary>See the output of <code>agent-cli wake-word-assistant --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli wake-word-assistant --help -->
<!-- echo '```' -->
<!-- CODE:END -->

</details>

### `interactive`

**Purpose:** A full-featured, conversational AI assistant that can interact with your system.

**Workflow:** This is a persistent, interactive agent that you can have a conversation with.

1.  Run the `interactive` command. It will start listening for your voice.
2.  Speak your command or question (e.g., "What's in my current directory?").
3.  The agent transcribes your speech, sends it to the LLM, and gets a response. The LLM can use tools like `read_file` or `execute_code` to answer your question.
4.  The agent speaks the response back to you and then immediately starts listening for your next command.
5.  The conversation continues in this loop. Conversation history is saved between sessions.

**Interaction Model:**

- **To Interrupt**: Press `Ctrl+C` **once** to stop the agent from either listening or speaking, and it will immediately return to a listening state for a new command. This is useful if it misunderstands you or you want to speak again quickly.
- **To Exit**: Press `Ctrl+C` **twice in a row** to terminate the application.

**How to Use It:**

- **Start the agent**: `agent-cli interactive --input-device-index 1 --tts`
- **Have a conversation**:
  - _You_: "Read the pyproject.toml file and tell me the project version."
  - _AI_: (Reads file) "The project version is 0.1.0."
  - _You_: "Thanks!"

<details>
<summary>See the output of <code>agent-cli interactive --help</code></summary>

<!-- CODE:BASH:START -->
<!-- echo '```yaml' -->
<!-- export NO_COLOR=1 -->
<!-- export TERM=dumb -->
<!-- export TERMINAL_WIDTH=90 -->
<!-- agent-cli interactive --help -->
<!-- echo '```' -->
<!-- CODE:END -->
<!-- OUTPUT:START -->
<!-- ⚠️ This content is auto-generated by `markdown-code-runner`. -->
```yaml

 Usage: agent-cli interactive [OPTIONS]

 An interactive agent that you can talk to.


╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --input-device-index  -i                       INTEGER  Index of the input   │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --input-device-name   -I                       TEXT     Name of the input    │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Microphone').        │
│                                                         [default: None]      │
│ --asr-provider                                 TEXT     ASR provider to use  │
│                                                         ("wyoming" or        │
│                                                         "openai").           │
│                                                         [default: wyoming]   │
│ --asr-server-ip                                TEXT     IP address of the    │
│                                                         ASR server.          │
│                                                         [default: localhost] │
│ --asr-server-port                              INTEGER  Port of the ASR      │
│                                                         server.              │
│                                                         [default: 10300]     │
│ --whisper-model                                TEXT     Name of the Whisper  │
│                                                         model to use.        │
│                                                         [default: whisper-1] │
│ --model               -m                       TEXT     Name of the model to │
│                                                         use.                 │
│                                                         [default:            │
│                                                         devstral:24b]        │
│ --ollama-host                                  TEXT     Ollama server host.  │
│                                                         [default:            │
│                                                         http://localhost:11… │
│ --llm-provider                                 TEXT     LLM provider to use  │
│                                                         ("ollama" or         │
│                                                         "openai").           │
│                                                         [default: ollama]    │
│ --openai-api-key                               TEXT     OpenAI API key.      │
│                                                         [default: None]      │
│ --stop                    --no-stop                     Stop the background  │
│                                                         process.             │
│                                                         [default: no-stop]   │
│ --status                  --no-status                   Check the status of  │
│                                                         the background       │
│                                                         process.             │
│                                                         [default: no-status] │
│ --toggle                  --no-toggle                   Toggle the           │
│                                                         background process   │
│                                                         on/off.              │
│                                                         [default: no-toggle] │
│ --enable-tts              --no-enable-tts               Enable               │
│                                                         text-to-speech       │
│                                                         output.              │
│                                                         [default:            │
│                                                         no-enable-tts]       │
│ --tts-server-ip                                TEXT     IP address of the    │
│                                                         TTS server.          │
│                                                         [default: localhost] │
│ --tts-server-port                              INTEGER  Port of the TTS      │
│                                                         server.              │
│                                                         [default: 10200]     │
│ --voice-name          -v                       TEXT     Name of the voice to │
│                                                         use for TTS.         │
│                                                         [default: None]      │
│ --tts-language                                 TEXT     Language to use for  │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --speaker                                      TEXT     Speaker to use for   │
│                                                         TTS.                 │
│                                                         [default: None]      │
│ --tts-speed                                    FLOAT    TTS speech speed.    │
│                                                         [default: 1.0]       │
│ --output-device-ind…  -o                       INTEGER  Index of the output  │
│                                                         device to use.       │
│                                                         [default: None]      │
│ --output-device-name  -O                       TEXT     Name of the output   │
│                                                         device to use (e.g., │
│                                                         'MacBook Pro         │
│                                                         Speakers').          │
│                                                         [default: None]      │
│ --save-file                                    PATH     Save audio to WAV    │
│                                                         file instead of      │
│                                                         playing it.          │
│                                                         [default: None]      │
│ --history-dir                                  PATH     Directory to store   │
│                                                         conversation         │
│                                                         history.             │
│                                                         [default:            │
│                                                         ~/.config/agent-cli… │
│ --last-n-messages                              INTEGER  Number of messages   │
│                                                         to include in the    │
│                                                         conversation         │
│                                                         history. Set to 0 to │
│                                                         disable history.     │
│                                                         [default: 50]        │
│ --log-level                                    TEXT     Set the log level    │
│                                                         (e.g., DEBUG, INFO,  │
│                                                         WARNING).            │
│                                                         [default: INFO]      │
│ --log-file                                     TEXT     Path to a file to    │
│                                                         write logs to.       │
│                                                         [default: None]      │
│ --list-devices            --no-list-devices             List available audio │
│                                                         devices and exit.    │
│                                                         [default:            │
│                                                         no-list-devices]     │
│ --quiet                   --no-quiet                    Suppress all output  │
│                                                         except for the final │
│                                                         result.              │
│                                                         [default: no-quiet]  │
│ --config-file                                  TEXT     Path to a custom     │
│                                                         config file.         │
│                                                         [default: None]      │
│ --help                                                  Show this message    │
│                                                         and exit.            │
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
