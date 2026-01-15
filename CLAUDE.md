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
- Keep CLI startup fast (<300ms) - use top-level imports by default, only use lazy imports when a heavy dependency actually causes slowdown
- External library assumptions (especially in `dev` command for terminals/editors/agents) must be backed by evidence (official docs, man pages, source code). Document evidence in test docstrings that also verify the implementation.

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

## Code Duplication Detection

This project uses two complementary tools to detect copy-paste code duplication:

1. **[jscpd](https://github.com/kucherenko/jscpd)** (primary) - Fast token-based detection with threshold
2. **[pylint duplicate-code](https://pylint.readthedocs.io/)** (secondary) - AST-based Python-specific detection

Both run as pre-commit hooks to catch duplicated code before it enters the codebase.

### Configuration

**jscpd** (`.jscpd.json`):
- **threshold**: 3% - Maximum allowed duplication percentage before failing
- **minLines**: 15 - Minimum lines for a block to be considered duplication
- **minTokens**: 100 - Minimum tokens for a block to be considered duplication

**pylint** (`pyproject.toml` → `[tool.pylint.similarities]`):
- **min-similarity-lines**: 70 - Catches very large duplications (safety net)
- Ignores comments, docstrings, imports, and signatures

### Running Manually

```bash
# jscpd - primary checker
npx jscpd --config .jscpd.json agent_cli/

# pylint - secondary checker
uv run pylint --disable=all --enable=duplicate-code agent_cli/

# Run both via pre-commit
pre-commit run jscpd --all-files
pre-commit run pylint-duplicate-code --all-files
```

### Ignoring Legitimate Duplicates

For jscpd (rare cases):
1. Add file patterns to the `ignore` array in `.jscpd.json`
2. Use `--ignore-pattern` for regex-based exclusions

For pylint:
1. Increase `min-similarity-lines` in `pyproject.toml` (not recommended)
2. Refactor the duplicated code (preferred)

Common legitimate duplicates (already excluded):
- Test files (`tests/**`, `test_*.py`)
- Scripts directory (`scripts/**`)

### Handling Violations

When duplication is reported:
1. Review the duplicated code blocks shown in the output
2. Extract common functionality into a shared module in `core/` or `services/`
3. Import and reuse the shared code from both locations

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
