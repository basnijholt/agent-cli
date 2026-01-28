# Server Command Help Improvements

## Summary

Improved help messages for `agent-cli server` command and all its subcommands (`whisper`, `transcribe-proxy`, `tts`) to be more informative for AI coding agents and users.

## Changes Made

### Main `server` Command
- Replaced minimal "Run ASR/TTS servers..." with comprehensive overview
- Added bullet list explaining each subcommand's purpose
- Added common workflow examples in a code block
- Mentioned Wyoming protocol and OpenAI API compatibility

### `server whisper` Subcommand
- **--model**: Listed common model names (tiny, base, small, medium, large-v3, distil-large-v3) with guidance on accuracy/speed tradeoffs
- **--default-model**: Clarified it must be in the `--model` list
- **--device**: Explained auto-detection and MLX backend behavior
- **--compute-type**: Explained precision tradeoffs (lower = faster + less VRAM)
- **--cache-dir**: Mentioned default is HuggingFace cache
- **--ttl**: Explained set to 0 keeps loaded indefinitely
- **--preload**: Explained benefit of reducing first-request latency
- **--host**: Clarified `0.0.0.0` for all interfaces
- **--port**: Mentioned the endpoint path (`/v1/audio/transcriptions`)
- **--wyoming-port**: Clarified Home Assistant integration
- **--no-wyoming**: Clarified it only runs HTTP API
- **--download-only**: Mentioned usefulness for Docker builds
- **--backend**: Explained auto-detection logic (faster-whisper vs MLX)

### `server transcribe-proxy` Subcommand
- **Complete docstring rewrite**: Removed unhelpful "This is the original server command functionality"
- Added clear explanation of when to use this vs `server whisper`
- Listed supported ASR providers (wyoming, openai, gemini)
- Listed supported LLM providers for cleanup (ollama, openai, gemini)
- Documented exposed endpoints (`POST /transcribe`, `GET /health`)
- Explained configuration sources (config file vs env vars)
- Added practical curl example for testing
- Improved option descriptions to match whisper style

### `server tts` Subcommand
- **--model**: Listed example voices for both Piper and Kokoro backends
- **--default-model**: Clarified it must be in the `--model` list
- **--device**: Explained Piper is CPU-only, Kokoro supports GPU
- **--cache-dir**: Mentioned default path (`~/.cache/agent-cli/tts/`)
- **--ttl**: Same improvement as whisper
- **--preload**: Same improvement as whisper
- **--host**: Same improvement as whisper
- **--port**: Mentioned the endpoint path (`/v1/audio/speech`)
- **--wyoming-port**: Same improvement as whisper
- **--no-wyoming**: Same improvement as whisper
- **--download-only**: Mentioned for models/voices, useful for Docker
- **--backend**: Explained each backend's characteristics (piper: CPU, many languages; kokoro: GPU, high quality)

## Observations

1. The existing docstrings for `whisper` and `tts` were already quite good - the main improvements were to option help text
2. `transcribe-proxy` had the weakest help and benefited most from the rewrite
3. The main `server` command was missing context about what each subcommand does and when to use it
4. Used `r"""` raw docstring for `transcribe-proxy` due to backslash in curl example
5. All tests pass (909 passed, 4 skipped)
6. Pre-commit hooks pass
7. Documentation auto-regenerated successfully
