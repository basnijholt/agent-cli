---
icon: lucide/settings
---

# config

Manage agent-cli configuration files.

## Usage

```bash
agent-cli config [OPTIONS] COMMAND [ARGS]...
```

## Description

The `config` command group helps you manage your `agent-cli` configuration. It allows you to initialize a template, view the current configuration, and edit it in your default editor.

## Commands

- `init`: Create a new config file template
- `show`: Display current configuration
- `edit`: Open config in your editor

### `config init`

Create a new config file with all options commented out.

```bash
agent-cli config init [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--path`, `-p` | Custom path for config file | `~/.config/agent-cli/config.toml` |
| `--force`, `-f` | Overwrite existing config without confirmation | `false` |

### `config show`

Display the config file location and contents.

```bash
agent-cli config show [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--path`, `-p` | Path to config file |
| `--raw`, `-r` | Output raw file contents (for copy-paste) |

### `config edit`

Open the config file in your default editor.

```bash
agent-cli config edit [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--path`, `-p` | Path to config file |

The editor is determined by: `$EDITOR` > `$VISUAL` > platform default.
