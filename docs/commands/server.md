---
icon: lucide/server
---

# server

Run the FastAPI transcription web server.

## Usage

```bash
agent-cli server [OPTIONS]
```

## Description

Starts a web server that provides HTTP endpoints for transcription services. This is useful for:

- Integrating transcription into web applications
- Running transcription as a service
- Remote access to transcription capabilities

## Examples

```bash
# Start server with defaults
agent-cli server

# Custom host and port
agent-cli server --host 127.0.0.1 --port 8080

# Development mode with auto-reload
agent-cli server --reload
```

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Host/IP to bind the server to | `0.0.0.0` |
| `--port` | Port to bind the server to | `61337` |
| `--reload` | Enable auto-reload for development | `false` |
| `--config` | Path to a TOML configuration file | - |
| `--print-args` | Print resolved arguments | - |

## Installation

Requires the `server` extra:

```bash
pip install "agent-cli[server]"
# or from repo
uv sync --extra server
```

## API Endpoints

The server exposes FastAPI endpoints for transcription. Visit `http://localhost:61337/docs` after starting for interactive API documentation.
