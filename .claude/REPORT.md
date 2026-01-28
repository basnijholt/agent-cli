# Config Command Help Improvements

## Summary

Improved help messages for `agent-cli config` and its subcommands to be more informative for users and AI coding agents.

## Changes Made

### Main `config` command
- Added explanation of TOML file format
- Listed config file search order (project-local first, then user default)
- Explained the `[defaults]` section and command-specific override sections
- Noted that CLI arguments override config file settings

### `config init` subcommand
- Updated description to mention "commented-out examples"
- Explained the template structure (`[defaults]` and command-specific sections)
- Added practical example: `agent-cli config init && agent-cli config edit`
- Improved `--path` help to clarify default location
- Improved `--force` help to mention "prompting for confirmation"

### `config edit` subcommand
- Documented the complete editor fallback chain: `$EDITOR` → `$VISUAL` → `nano`/`vim` → `vi` (or `notepad` on Windows)
- Added guidance to run `config init` first if no config exists
- Improved `--path` help to describe behavior more clearly

### `config show` subcommand
- Updated description to mention "active config file"
- Explained default behavior (syntax highlighting, line numbers)
- Added use cases for `--raw` (piping) and `--json` (programmatic access)
- Improved `--json` help to list the output fields: `path`, `exists`, `content`
- Improved `--raw` help to clarify what it omits (highlighting and line numbers)

## Files Modified

- `agent_cli/config_cmd.py` - All help text improvements
- `docs/commands/config.md` - Auto-regenerated from CLI introspection

## Observations

- The config command structure is clean and well-organized
- The example-config.toml file is comprehensive and serves as good documentation
- Config file search order (project-local before user default) is useful for per-project overrides
