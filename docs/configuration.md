---
icon: lucide/settings
---

# Configuration

All `agent-cli` commands can be configured using a TOML file. The configuration file is searched for in the following locations, in order:

1. `./agent-cli-config.toml` (in the current directory)
2. `~/.config/agent-cli/config.toml`

You can also specify a path to a configuration file using the `--config` option:

```bash
agent-cli transcribe --config /path/to/your/config.toml
```

Command-line options always take precedence over settings in the configuration file.

Option keys can be written with dashes (matching CLI flags) or underscores; both
are accepted.

## Managing Configuration

Use the [`config`](commands/config.md) command to manage your configuration files:

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

## Related

- [Commands Reference](commands/index.md) - Command-specific flags and usage
- [Architecture](architecture/index.md) - How configuration is loaded and applied
- [memory](commands/memory.md) - Memory proxy config keys
- [rag-proxy](commands/rag-proxy.md) - RAG proxy config keys

## Example Configuration

Here's an example configuration file showing common options:

```toml
[defaults]
# Provider defaults (can be overridden per command)
# llm_provider = "ollama"
# asr_provider = "wyoming"
# tts_provider = "wyoming"

# OpenAI API key (if using OpenAI services)
# openai_api_key = "sk-..."

[transcribe]
# Audio input device index (use --list-devices to find yours)
# input_device_index = 1

# Use LLM to clean up transcription
# llm = true

# Save recordings for recovery
# save_recording = true

[autocorrect]
# LLM provider: 'ollama', 'openai', or 'gemini'
# llm_provider = "ollama"

[speak]
# TTS provider: 'wyoming', 'openai', 'kokoro', or 'gemini'
# tts_provider = "wyoming"

# Speech speed multiplier
# tts_speed = 1.0

[voice-edit]
# Enable TTS for responses
# enable_tts = false

[assistant]
# Wake word for activation
# wake_word = "ok_nabu"

[chat]
# Number of messages to keep in history
# last_n_messages = 50
```

## Provider Defaults

You can choose local or cloud services per capability by setting provider keys in
`[defaults]` (or in a command-specific section to override).

```toml
[defaults]
llm_provider = "ollama"  # 'ollama', 'openai', or 'gemini'
asr_provider = "wyoming" # 'wyoming', 'openai', or 'gemini'
tts_provider = "wyoming" # 'wyoming', 'openai', 'kokoro', or 'gemini'
# openai_api_key = "sk-..."  # Required for OpenAI providers
# gemini_api_key = "..."     # Required for Gemini providers
```

`local` is a deprecated alias for `ollama` (LLM) and `wyoming` (ASR/TTS).

## Provider-Specific Configuration

### Ollama (Local LLM)

```toml
[defaults]
# Model to use for LLM tasks
llm_ollama_model = "gemma3:4b"

# Ollama server host
llm_ollama_host = "http://localhost:11434"
```

### OpenAI

```toml
[defaults]
# LLM model
llm_openai_model = "gpt-5-mini"

# ASR model
asr_openai_model = "whisper-1"

# TTS model and voice
tts_openai_model = "tts-1"
tts_openai_voice = "alloy"

# API key (can also use OPENAI_API_KEY env var)
# openai_api_key = "sk-..."

# Custom base URL for OpenAI-compatible LLM APIs
# openai_base_url = "http://localhost:8080/v1"

# Custom ASR endpoint and optional prompt
# asr_openai_base_url = "http://localhost:9898"
# asr_openai_prompt = "Transcribe the following:"

# Custom TTS endpoint
# tts_openai_base_url = "http://localhost:8000/v1"
```

### Gemini

```toml
[defaults]
# LLM model
llm_gemini_model = "gemini-3-flash-preview"

# ASR model
asr_gemini_model = "gemini-3-flash-preview"

# TTS model and voice
tts_gemini_model = "gemini-2.5-flash-preview-tts"
tts_gemini_voice = "Kore"

# API key (can also use GEMINI_API_KEY env var)
# gemini_api_key = "..."
```

### Wyoming (Local Services)

```toml
[defaults]
# ASR (Whisper) server
asr_wyoming_ip = "localhost"
asr_wyoming_port = 10300

# TTS (Piper) server
tts_wyoming_ip = "localhost"
tts_wyoming_port = 10200
# tts_wyoming_voice = "en_US-lessac-medium"  # Optional: specify voice

# Wake word server
wake_server_ip = "localhost"
wake_server_port = 10400
```

### Kokoro (Local TTS)

```toml
[defaults]
tts_kokoro_host = "http://localhost:8880/v1"
tts_kokoro_model = "kokoro"
tts_kokoro_voice = "af_sky"
```

## Using Local Whisper Server

Run your own GPU-accelerated Whisper server for free, private, offline transcription.

### Quick Start

```bash
# Terminal 1: Start the server
agent-cli server whisper

# Terminal 2: Transcribe using local server (Wyoming streams audio in real-time)
agent-cli transcribe --asr-provider wyoming --asr-wyoming-port 10300
```

That's it! The server loads the model on first request and auto-unloads after 5 minutes of idle time to free VRAM.

### Make It Permanent

Add to your config file so all commands use your local server:

```toml
[defaults]
asr_provider = "wyoming"
asr_wyoming_port = 10300
```

Now just run `agent-cli transcribe` - it automatically uses your local server.

### Why Use This?

| Benefit | Description |
|---------|-------------|
| **Private** | Audio never leaves your machine |
| **Fast** | GPU acceleration, no network latency |
| **Streaming** | Wyoming streams audio as you speak (lower latency) |
| **Offline** | Works without internet |
| **VRAM-friendly** | Auto-unloads when idle |

> [!TIP]
> **OpenAI SDK users:** The server also exposes an OpenAI-compatible API on port 10301.
> See [server whisper docs](commands/server/whisper.md) for all options.

## Audio Device Configuration

```toml
[defaults]
# Input device index (microphone)
# Use 'agent-cli transcribe --list-devices' to find available devices
input_device_index = 1

# Or use partial name matching
# input_device_name = "MacBook Pro Microphone"

# Output device index (speakers)
output_device_index = 0

# Or use partial name matching
# output_device_name = "External Speakers"
```

## Environment Variables

Many settings can also be configured via environment variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible API URL |
| `GEMINI_API_KEY` | Google Gemini API key |

## Logging Configuration

```toml
[defaults]
# Log level: DEBUG, INFO, WARNING, ERROR
log_level = "WARNING"

# Log to file
# log_file = "/path/to/agent-cli.log"

# Suppress rich console output
# quiet = false
```

## Command-Specific Settings

Each command has its own section in the config file. The section name matches the
command name, and subcommands use dot notation:

- `[transcribe]` - for [`agent-cli transcribe`](commands/transcribe.md)
- `[voice-edit]` - for [`agent-cli voice-edit`](commands/voice-edit.md)
- `[transcribe-daemon]` - for [`agent-cli transcribe-daemon`](commands/transcribe-daemon.md)
- `[memory.proxy]` - for [`agent-cli memory proxy`](commands/memory.md)

Use `agent-cli <command> --help` to see all available options for each command, or browse the [Commands Reference](commands/index.md).
