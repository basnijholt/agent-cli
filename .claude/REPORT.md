# Improved Help Messages for `chat` Command

## Summary

Improved the `agent-cli chat` command help messages to be more informative for AI coding agents and users.

## Changes Made

### 1. Main Command Docstring (`agent_cli/agents/chat.py`)

**Before:**
```
An chat agent that you can talk to.
```

**After:**
- Fixed grammatical error ("An chat" → proper description)
- Added clear explanation of the interactive loop: listen → transcribe → LLM → speak response
- Documented built-in tools (memory, web search, file access, code execution)
- Explained process management options (`--toggle`, `--stop`, `--status`)
- Added three practical examples showing common use cases

### 2. History Options Help Text

**`--history-dir`:**
- Before: "Directory to store conversation history."
- After: "Directory for conversation history and long-term memory. Both `conversation.json` and `long_term_memory.json` are stored here."

**`--last-n-messages`:**
- Before: "Number of messages to include in the conversation history. Set to 0 to disable history."
- After: "Number of past messages to include as context for the LLM. Set to 0 to start fresh each session (memory tools still persist)."

## Observations

1. The chat command has significant functionality that wasn't visible in the help:
   - Built-in tools for memory, web search, file reading, and code execution
   - Long-term memory persistence separate from conversation history
   - Background process management for hotkey integration

2. The relationship between `--history-dir` and the memory tools was not documented - both the conversation history and long-term memory files are stored in the same directory.

3. The distinction between conversation history (ephemeral context) and long-term memory (persistent) wasn't clear. Updated help text now clarifies that setting `--last-n-messages 0` starts fresh each session but memory tools still persist.

## Testing

- All 909 tests pass
- Pre-commit hooks pass
- Documentation regenerated
- Help output verified
