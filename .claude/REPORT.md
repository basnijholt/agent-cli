# Report: Improved transcribe command help messages

## Summary

Improved the help messages for the `transcribe` command to be more informative for AI coding agents and users.

## Changes Made

### Main docstring (`agent_cli/agents/transcribe.py`)

- Replaced the generic "Wyoming ASR Client" description with a clear explanation of what the command does
- Added explanation of key features (`--llm` for cleanup, `--toggle` for hotkey binding)
- Added practical examples showing common usage patterns

### LLM Configuration options

- **`--llm`**: Changed from "Use an LLM to process the transcript" to "Clean up transcript with LLM: fix errors, add punctuation, remove filler words"
- **`--extra-instructions`**: Clarified that it requires `--llm` to work

### Process Management options (`agent_cli/opts.py`)

- **`--stop`**: Clarified that it sends SIGINT to trigger transcription
- **`--status`**: Changed to "Check if an instance is currently recording"
- **`--toggle`**: Made it clear this is ideal for hotkey binding

### Audio Recovery options

- **`--from-file`**: Restructured for clarity, noted ffmpeg requirement
- **`--last-recording`**: Added practical use case (retry with `--llm` or different provider)
- **`--save-recording`**: Mentioned the actual storage location (`~/.cache/agent-cli/`)

### Audio Input options

- **`--input-device-index`**: Added reference to `--list-devices` and noted system default behavior
- **`--input-device-name`**: Added example substrings (`MacBook`, `USB`)
- **`--list-devices`**: Simplified and clarified

### General Options

- **`--json`**: Added the actual JSON keys (`raw_transcript`, `transcript`, `llm_enabled`)
- **`--transcription-log`**: Explained the JSONL format and that recent entries provide context for LLM cleanup

## Observations

1. The changes affect multiple commands since most options are shared via `opts.py`. This is intentional as these improvements apply to all commands using these options.

2. The transcription log feature has a nice but non-obvious behavior: recent log entries are automatically provided as context to the LLM for better cleanup. This is now documented.

3. The `--toggle` option is particularly useful for hotkey binding but this wasn't clear from the original help text. Now it explicitly mentions this use case.
