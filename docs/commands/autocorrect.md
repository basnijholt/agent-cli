---
icon: lucide/check-circle
---

# autocorrect

Correct grammar and spelling in text using a local or remote LLM.

## Usage

```bash
agent-cli autocorrect [TEXT]
```

## Description

This is a simple, one-shot command that:

1. Reads text from your system clipboard (or from a direct argument)
2. Sends the text to an LLM with a prompt to perform only technical corrections
3. Copies the corrected text back to your clipboard, replacing the original

This tool is ideal for integrating with a system-wide hotkey.

## Examples

```bash
# Correct text from clipboard
agent-cli autocorrect

# Correct text from argument
agent-cli autocorrect "this text has an eror"
```

## Options

### Provider Selection

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-provider` | LLM provider: `ollama`, `openai`, `gemini` | `ollama` |

### Ollama Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-ollama-model` | Ollama model to use | `gemma3:4b` |
| `--llm-ollama-host` | Ollama server URL | `http://localhost:11434` |

### OpenAI Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-openai-model` | OpenAI model to use | `gpt-5-mini` |
| `--openai-api-key` | OpenAI API key | `$OPENAI_API_KEY` |
| `--openai-base-url` | Custom OpenAI-compatible API URL | - |

### Gemini Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--llm-gemini-model` | Gemini model to use | `gemini-2.5-flash` |
| `--gemini-api-key` | Gemini API key | `$GEMINI_API_KEY` |

## Workflow Integration

### System-Wide Hotkey

Set up a hotkey to run autocorrect on your clipboard:

=== "macOS (skhd)"

    ```
    cmd + shift + a : /path/to/agent-cli autocorrect
    ```

=== "Linux (Hyprland)"

    ```
    bind = SUPER SHIFT, A, exec, agent-cli autocorrect
    ```

### Typical Usage

1. Select and copy text with errors
2. Press your hotkey (e.g., Cmd+Shift+A)
3. Paste the corrected text
