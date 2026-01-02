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

The `config` command helps you create, edit, and inspect your configuration file.

## Commands

- `config init` - Create a new config template
- `config edit` - Open the config file in your editor
- `config show` - Print the config file path and contents

---

## config init

Create a new config file with all options commented out.

### Usage

```bash
agent-cli config init [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--path`, `-p` | Custom path for config file | `~/.config/agent-cli/config.toml` |
| `--force`, `-f` | Overwrite existing config without confirmation | `false` |

### Example

```bash
agent-cli config init
```

---

## config edit

Open the config file in your default editor.

### Usage

```bash
agent-cli config edit [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--path`, `-p` | Path to config file (auto-detected if not specified) | - |

### Example

```bash
agent-cli config edit
```

---

## config show

Display the config file location and contents.

### Usage

```bash
agent-cli config show [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--path`, `-p` | Path to config file (auto-detected if not specified) | - |
| `--raw`, `-r` | Output raw file contents (for copy-paste) | `false` |

### Example

```bash
agent-cli config show --raw
```
