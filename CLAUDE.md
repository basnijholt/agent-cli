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
- Keep CLI startup fast (<300ms) - use top-level imports by default for first-party and stdlib imports, use lazy imports for ALL 3rd party dependencies (except pydantic, typer, and rich)
- External library assumptions (especially in `dev` command for terminals/editors/agents) must be backed by evidence (official docs, man pages, source code). Document evidence in test docstrings that also verify the implementation.
- Private functions (`_name`) don't need parameter documentation in docstrings - a one-line description is sufficient

## Build & Development Commands

```bash
uv sync --all-extras                           # Install with all extras (rag, memory, vad)
uv run python docs/run_markdown_code_runner.py # Update auto-generated docs
```

## Architecture Overview

### CLI Structure

The CLI is built with **Typer**. Entry point is `agent_cli/cli.py` which registers all commands.

**Shared Options Pattern**: Common CLI options (providers, API keys, audio devices) are defined once in `agent_cli/opts.py` and reused across commands. This ensures consistency and enables auto-generated documentation.

### Provider Abstraction

The codebase uses a **provider pattern** for AI services, allowing switching between local and cloud backends:

| Capability | Providers | Implementation |
|------------|-----------|----------------|
| ASR (Speech-to-Text) | `wyoming`, `openai`, `gemini` | `services/asr.py` |
| LLM | `ollama`, `openai`, `gemini` | `services/llm.py` |
| TTS (Text-to-Speech) | `wyoming`, `openai`, `kokoro`, `gemini` | `services/tts.py` |

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
│   └── tts.py          # Wyoming/OpenAI/Kokoro/Gemini TTS
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

The `docs_gen` module introspects Typer commands to generate Markdown tables. Documentation files use [markdown-code-runner](https://github.com/basnijholt/markdown-code-runner) markers:

```markdown
<!-- CODE:START -->
<!-- from agent_cli.docs_gen import all_options_for_docs -->
<!-- print(all_options_for_docs("transcribe")) -->
<!-- CODE:END -->
```

Run `uv run python docs/run_markdown_code_runner.py` to regenerate all auto-generated content.

## Releases

Use `gh release create` to create releases. The tag is created automatically.

```bash
# IMPORTANT: Ensure you're on latest origin/main before releasing!
git fetch origin
git checkout origin/main

# Check current version
git tag --sort=-v:refname | head -1

# Create release (minor version bump: v0.21.1 -> v0.22.0)
gh release create v0.22.0 --title "v0.22.0" --notes "release notes here"
```

Versioning:
- **Patch** (v0.21.0 → v0.21.1): Bug fixes
- **Minor** (v0.21.1 → v0.22.0): New features, non-breaking changes

Write release notes manually describing what changed. Group by features and bug fixes.
