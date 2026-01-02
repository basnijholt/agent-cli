---
icon: lucide/play-circle
---

# start-services

Start all agent-cli services in a Zellij session.

## Usage

```bash
agent-cli start-services [OPTIONS]
```

## Description

This starts all installed AI services (Ollama, Whisper, Piper, OpenWakeWord) in a single terminal session using [Zellij](https://zellij.dev/).

It creates a Zellij session named `agent-cli` and attaches to it. You can detach from the session (leaving services running in the background) or quit to stop them.

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--attach` / `--no-attach` | Attach to Zellij session after starting | `true` |

## Controls

Once inside the Zellij session:
- **Detach**: Press `Ctrl + o`, then `d` (leaves services running)
- **Quit**: Press `Ctrl + q` (stops all services)
- **Navigate**: Use `Alt + arrow keys` to switch between service panes

## Reattaching

If you detached or used `--no-attach`, you can reconnect later:

```bash
zellij attach agent-cli
```
