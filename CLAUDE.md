# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Rules

- Prefer functional style Python over classes with inheritance
- Keep it DRY - reuse code, check for existing patterns before adding new ones
- Implement the simplest solution; don't generalize until needed
- Only implement what's asked for, nothing extra
- Always run `pytest` before claiming a task is done
- Run `pre-commit run --all-files` before committing
- Use `git add <specific-file>` not `git add .`
- CLI help in README.md is auto-generated - don't edit manually

## Build & Development Commands

```bash
# Install all dependencies (recommended for development)
uv sync --all-extras

# Or install specific extras only
uv sync --extra rag      # RAG proxy dependencies
uv sync --extra memory   # Memory proxy dependencies
uv sync --extra vad      # Voice activity detection (transcribe-daemon)

# Run the CLI during development
uv run agent-cli <command>

# Run tests (coverage enabled by default via pyproject.toml)
uv run pytest

# Linting (pre-commit runs ruff + other checks)
pre-commit run --all-files

# Update auto-generated documentation (CODE:START blocks in markdown)
uv run python docs/update_docs.py
```

## Architecture Overview

### CLI Structure

The CLI is built with **Typer**. Entry point is `agent_cli/cli.py` which registers all commands.

**Shared Options Pattern**: Common CLI options (providers, API keys, audio devices) are defined once in `agent_cli/opts.py` and reused across commands. This ensures consistency and enables auto-generated documentation.

### Provider Abstraction

The codebase uses a **provider pattern** for AI services, allowing switching between local and cloud backends:

| Capability | Providers | Implementation |
|------------|-----------|----------------|
| ASR (Speech-to-Text) | `wyoming`, `openai` | `services/asr.py` |
| LLM | `ollama`, `openai`, `gemini` | `services/llm.py` |
| TTS (Text-to-Speech) | `wyoming`, `openai`, `kokoro` | `services/tts.py` |

Each agent accepts `--{asr,llm,tts}-provider` flags to select the backend.

### Key Modules

```
agent_cli/
├── cli.py              # Typer app, command registration
├── opts.py             # Shared CLI option definitions (single source of truth)
├── config.py           # Config file loading, dataclasses for typed configs
├── agents/             # CLI commands (one file per command)
│   ├── transcribe.py   # Voice-to-text with optional LLM cleanup
│   ├── autocorrect.py  # Grammar/spelling correction
│   ├── chat.py         # Conversational agent with tools
│   ├── voice_edit.py   # Voice commands on clipboard text
│   └── ...
├── services/           # Provider implementations
│   ├── asr.py          # Wyoming/OpenAI transcription
│   ├── llm.py          # Ollama/OpenAI/Gemini LLM calls
│   └── tts.py          # Wyoming/OpenAI/Kokoro TTS
├── core/               # Shared utilities
│   ├── audio.py        # Audio recording, device selection
│   ├── process.py      # Background process management (--toggle, --stop)
│   └── utils.py        # Console output, logging setup
├── rag/                # RAG proxy server implementation
├── memory/             # Long-term memory proxy server
└── docs_gen.py         # Auto-generates docs from CLI introspection
```

### Agent Pattern

Each agent in `agents/` follows a consistent pattern:
1. Import shared options from `opts.py`
2. Define a Typer command decorated with `@app.command()`
3. Use `config.py` dataclasses to group related options
4. Call provider services from `services/`

### Background Process Management

Commands like `transcribe`, `voice-edit`, and `chat` support running as background processes with hotkey integration:
- `--toggle`: Start if stopped, stop if running
- `--stop`: Stop any running instance
- `--status`: Check if running

PID files are stored in `~/.cache/agent-cli/`.

### Documentation Auto-Generation

The `docs_gen` module introspects Typer commands to generate Markdown tables. Documentation files use `markdown-code-runner` markers:

```markdown
<!-- CODE:START -->
<!-- from agent_cli.docs_gen import all_options_for_docs -->
<!-- print(all_options_for_docs("transcribe")) -->
<!-- CODE:END -->
```

Run `uv run python docs/update_docs.py` to regenerate all auto-generated content.
