---
icon: lucide/brain
---

# memory

Long-term memory system for conversations with subcommands for memory management.

## Commands

- [`memory proxy`](#memory-proxy) - Long-term memory chat proxy server
- [`memory add`](#memory-add) - Add memories directly without LLM extraction

---

## memory proxy

A middleware server that gives any OpenAI-compatible app long-term memory.

### Usage

```bash
agent-cli memory proxy [OPTIONS]
```

### Description

Acts as a proxy between your chat client and an LLM provider:

1. Intercepts chat requests
2. Retrieves relevant memories from a local vector database
3. Injects memories into the system prompt
4. Forwards the augmented request to the LLM
5. Extracts new facts from the conversation and stores them

### Key Features

- **Simple Markdown Files**: Memories stored as human-readable Markdown
- **Automatic Version Control**: Built-in Git integration
- **Lightweight & Local**: Runs entirely on your machine
- **Proxy Middleware**: Works with any OpenAI-compatible endpoint

### Installation

```bash
pip install "agent-cli[memory]"
# or from repo
uv sync --extra memory
```

### Examples

```bash
# With local LLM (Ollama)
agent-cli memory proxy \
  --memory-path ./memory_db \
  --openai-base-url http://localhost:11434/v1 \
  --embedding-model embeddinggemma:300m

# Use with agent-cli chat
agent-cli chat --openai-base-url http://localhost:8100/v1 --llm-provider openai
```

### Options

#### Memory Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--memory-path PATH` | Path to memory store | `./memory_db` |
| `--default-top-k N` | Memories to retrieve per query | `5` |
| `--max-entries N` | Max entries per conversation | `500` |
| `--mmr-lambda FLOAT` | MMR lambda (0-1): relevance vs diversity | `0.7` |
| `--recency-weight FLOAT` | Recency score weight (0-1) | `0.2` |
| `--score-threshold FLOAT` | Min semantic relevance threshold | `0.35` |
| `--summarization` / `--no-summarization` | Enable fact extraction & summaries | `true` |
| `--git-versioning` / `--no-git-versioning` | Enable git commits for changes | `true` |

#### LLM Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--openai-base-url` | OpenAI-compatible API URL | - |
| `--openai-api-key` | OpenAI API key | - |
| `--embedding-model` | Model for embeddings | `text-embedding-3-small` |

#### Server Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host to bind to | `0.0.0.0` |
| `--port` | Port to bind to | `8100` |

#### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--log-level` | Logging level | `INFO` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

---

## memory add

Add memories directly to the store without LLM extraction.

### Usage

```bash
agent-cli memory add [MEMORIES]... [OPTIONS]
```

### Description

Useful for bulk imports or seeding memories. The memory proxy file watcher will auto-index new files.

### Examples

```bash
# Add single memories as arguments
agent-cli memory add "User likes coffee" "User lives in Amsterdam"

# Read from JSON file
agent-cli memory add -f memories.json

# Read from stdin (plain text, one per line)
echo "User prefers dark mode" | agent-cli memory add -f -

# Read JSON from stdin
echo '["Fact one", "Fact two"]' | agent-cli memory add -f -

# Specify conversation ID
agent-cli memory add -c work "Project deadline is Friday"
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-f`, `--file PATH` | Read from file (use `-` for stdin) | - |
| `-c`, `--conversation-id` | Conversation ID to add memories to | `default` |
| `--memory-path PATH` | Path to memory store | `./memory_db` |
| `--git-versioning` / `--no-git-versioning` | Commit changes to git | `true` |

### General Options

| Option | Description | Default |
|--------|-------------|---------|
| `--quiet`, `-q` | Suppress console output | `false` |
| `--config PATH` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments including config values | `false` |

### File Format

Supports:
- JSON array: `["fact 1", "fact 2"]`
- JSON object with `memories` key: `{"memories": ["fact 1", "fact 2"]}`
- Plain text (one fact per line)

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Your Client   │────▶│  Memory Proxy   │────▶│   LLM Backend   │
│                 │◀────│  :8100          │◀────│                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
           ┌────────▼───┐  ┌─────▼─────┐  ┌───▼───────┐
           │  ChromaDB  │  │ Markdown  │  │    Git    │
           │  (Vector)  │  │  (Files)  │  │ (Version) │
           └────────────┘  └───────────┘  └───────────┘
```

## Memory Files

Stored as Markdown under `{memory-path}/entries/<conversation_id>/`:

```
entries/
  <conversation_id>/
    facts/
      <timestamp>__<uuid>.md
    turns/
      user/<timestamp>__<uuid>.md
      assistant/<timestamp>__<uuid>.md
    summaries/
      summary.md
```

See `docs/architecture/memory.md` for the full schema and metadata format.
