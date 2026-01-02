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

## Managing Configuration

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

## Example Configuration

Here's an example configuration file showing common options:

```toml
[defaults]
# Service provider: 'ollama' for local or 'openai' for cloud
# service_provider = "ollama"

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
# TTS provider: 'wyoming', 'openai', or 'kokoro'
# tts_provider = "wyoming"

# Speech speed multiplier
# tts_speed = 1.0

[voice_edit]
# Enable TTS for responses
# tts = false

[assistant]
# Wake word for activation
# wake_word = "ok_nabu"

[chat]
# Number of messages to keep in history
# last_n_messages = 50
```

## Service Provider

You can choose to use local services (Wyoming/Ollama) or cloud services (OpenAI) by setting the `service_provider` option:

```toml
[defaults]
service_provider = "ollama"  # 'ollama' or 'openai'
# openai_api_key = "sk-..."  # Required if using 'openai'
```

## Provider-Specific Configuration

### Ollama (Local LLM)

```toml
[ollama]
# Model to use for LLM tasks
llm_ollama_model = "gemma3:4b"

# Ollama server host
llm_ollama_host = "http://localhost:11434"
```

### OpenAI

```toml
[openai]
# LLM model
llm_openai_model = "gpt-5-mini"

# ASR model
asr_openai_model = "whisper-1"

# TTS model and voice
tts_openai_model = "tts-1"
tts_openai_voice = "alloy"

# API key (can also use OPENAI_API_KEY env var)
# openai_api_key = "sk-..."

# Custom base URL for OpenAI-compatible APIs
# openai_base_url = "http://localhost:8080/v1"
```

### Gemini

```toml
[gemini]
# Gemini model
llm_gemini_model = "gemini-2.5-flash"

# API key (can also use GEMINI_API_KEY env var)
# gemini_api_key = "..."
```

### Wyoming (Local Services)

```toml
[wyoming]
# ASR (Whisper) server
asr_wyoming_ip = "localhost"
asr_wyoming_port = 10300

# TTS (Piper) server
tts_wyoming_ip = "localhost"
tts_wyoming_port = 10200
tts_wyoming_voice = "en_US-lessac-medium"

# Wake word server
wake_server_ip = "localhost"
wake_server_port = 10400
```

### Kokoro (Local TTS)

```toml
[kokoro]
tts_kokoro_host = "http://localhost:8880/v1"
tts_kokoro_model = "kokoro"
tts_kokoro_voice = "af_sky"
```

## Audio Device Configuration

```toml
[audio]
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
[logging]
# Log level: DEBUG, INFO, WARNING, ERROR
log_level = "WARNING"

# Log to file
# log_file = "/path/to/agent-cli.log"

# Suppress rich console output
# quiet = false
```

## Command-Specific Settings

Each command has its own section in the config file. The section name matches the command name with underscores instead of hyphens:

- `[transcribe]` - for `agent-cli transcribe`
- `[voice_edit]` - for `agent-cli voice-edit`
- `[transcribe_daemon]` - for `agent-cli transcribe-daemon`

Use `agent-cli <command> --help` to see all available options for each command.
