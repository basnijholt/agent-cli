# Speak Command Help Improvements Report

## Summary

Improved help messages for the `agent-cli speak` command to be more informative for AI coding agents and users.

## Changes Made

### 1. Main Command Docstring (`agent_cli/agents/speak.py`)

**Before:**
```
Convert text to speech using Wyoming or OpenAI-compatible TTS server.
```

**After:**
```
Convert text to speech and play audio through speakers.

By default, synthesized audio plays immediately. Use --save-file to save
to a WAV file instead (skips playback).

Text can be provided as an argument or read from clipboard automatically.

Examples:

Speak text directly:
    agent-cli speak "Hello, world!"

Speak clipboard contents:
    agent-cli speak

Save to file instead of playing:
    agent-cli speak "Hello" --save-file greeting.wav

Use OpenAI TTS:
    agent-cli speak "Hello" --tts-provider openai
```

### 2. Text Argument Help

**Before:** `Text to speak. Reads from clipboard if not provided.`
**After:** `Text to synthesize. If not provided, reads from clipboard.`

### 3. Shared Options (`agent_cli/opts.py`)

- **`--save-file`**: Changed from "Save TTS response audio to WAV file." to "Save audio to WAV file instead of playing through speakers." (clarifies the behavior that playback is skipped)

- **`--output-device-index`**: Changed from "Index of the audio output device to use for TTS." to "Audio output device index (see `--list-devices` for available devices)." (references the discovery command)

- **`--output-device-name`**: Changed from "Output device name keywords for partial matching." to "Partial match on device name (e.g., 'speakers', 'headphones')." (provides concrete examples)

- **`--tts-openai-voice`**: Changed from "The voice to use for OpenAI-compatible TTS." to "Voice for OpenAI TTS (alloy, echo, fable, onyx, nova, shimmer)." (lists available voices inline)

## Observations

1. The `speak` command shares many options with other TTS-enabled commands through `opts.py`. Improvements to shared options benefit multiple commands (chat, voice-edit, etc.).

2. The command has useful process management features (`--toggle`, `--stop`, `--status`) that could be highlighted more, but these are already well-documented in the Process Management panel.

3. The examples in the docstring cover the most common use cases: direct text, clipboard, saving to file, and switching providers.

## Verification

- All 909 tests pass
- Pre-commit hooks pass
- Documentation regenerated successfully
- Help output renders correctly with Markdown formatting
