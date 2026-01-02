---
icon: lucide/edit
---

# voice-edit

A voice-powered clipboard assistant that edits text based on spoken commands.

## Usage

```bash
agent-cli voice-edit [OPTIONS]
```

## Description

This command is designed for a hotkey-driven workflow to act on text you've already copied:

1. Copy a block of text to your clipboard (e.g., an email draft)
2. Press a hotkey to start the agent—it begins listening
3. Speak a command: "Make this more formal" or "Summarize the key points"
4. Press the hotkey again to stop recording
5. The agent transcribes your command, sends it with the clipboard text to the LLM
6. The result is copied back to your clipboard
7. Optionally speaks the result if `--tts` is enabled

## Examples

```bash
# Run in foreground
agent-cli voice-edit --input-device-index 1

# Run in background (for hotkey integration)
agent-cli voice-edit --input-device-index 1 &

# With text-to-speech response
agent-cli voice-edit --tts

# Check status
agent-cli voice-edit --status

# Stop background process
agent-cli voice-edit --stop
```

## Options

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--asr-provider` | ASR provider: `wyoming`, `openai` | `wyoming` |
| `--llm-provider` | LLM provider: `ollama`, `openai`, `gemini` | `ollama` |
| `--tts-provider` | TTS provider: `wyoming`, `openai`, `kokoro` | `wyoming` |

### Audio Configuration

| Option | Description |
|--------|-------------|
| `--input-device-index` | Index of audio input device |
| `--input-device-name` | Input device name keywords |
| `--output-device-index` | Index of audio output device |
| `--output-device-name` | Output device name keywords |
| `--list-devices` | List available devices |

### TTS Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tts` / `--no-tts` | Enable text-to-speech response | `false` |
| `--tts-speed` | Speech speed multiplier | `1.0` |
| `--save-file PATH` | Save TTS audio to file | - |

### Output Options

| Option | Description | Default |
|--------|-------------|---------|
| `--clipboard` / `--no-clipboard` | Copy result to clipboard | `true` |

### Process Management

| Option | Description |
|--------|-------------|
| `--stop` | Stop running background process |
| `--status` | Check if process is running |
| `--toggle` | Toggle process on/off |

## Hotkey Integration

### macOS (skhd)

```
# Toggle voice-edit with Cmd+Shift+V
cmd + shift + v : /path/to/agent-cli voice-edit --toggle --input-device-index 1
```

### Linux (Hyprland)

```
bind = SUPER SHIFT, V, exec, agent-cli voice-edit --toggle --input-device-index 1
```

## Example Commands

Once activated, you can give commands like:

- "Make this more formal"
- "Summarize the key points"
- "Fix the grammar"
- "Translate to Spanish"
- "Make it shorter"
- "Add bullet points"
- "Rewrite for a technical audience"

## Workflow Example

1. **Copy an email draft:**
   ```
   hey can u help me with the project tmrw?
   ```

2. **Press hotkey, speak:** "Make this professional"

3. **Press hotkey again to stop**

4. **Paste the result:**
   ```
   Hello,

   Would you be available to assist me with the project tomorrow?

   Best regards
   ```
