"""Documentation generators for markdown-code-runner integration.

This module provides functions to introspect Typer commands and generate
Markdown documentation. Use with markdown-code-runner to auto-generate
options tables in documentation.

Example usage in Markdown files:
    <!-- CODE:START -->
    <!-- from agent_cli.docs_gen import all_options_for_docs -->
    <!-- print(all_options_for_docs("transcribe")) -->
    <!-- CODE:END -->
    <!-- OUTPUT:START -->
    ...auto-generated table...
    <!-- OUTPUT:END -->
"""

from __future__ import annotations

from typing import Any, get_origin

import click
from typer.main import get_command

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.install.extras import EXTRAS


def _get_type_str(annotation: Any) -> str:
    """Convert a type annotation to a readable string."""
    if annotation is None:
        return "str"

    # Handle Optional types (Union[X, None])
    origin = get_origin(annotation)
    if origin is type(None):
        return "None"

    # Get the base type name
    if hasattr(annotation, "__name__"):
        return annotation.__name__.upper()
    if hasattr(annotation, "__origin__"):
        # Handle generic types like Optional[str]
        args = getattr(annotation, "__args__", ())
        non_none_args = [a for a in args if a is not type(None)]
        if non_none_args:
            return _get_type_str(non_none_args[0])
    return str(annotation).replace("typing.", "").upper()


def _format_default(default: Any) -> str:
    """Format a default value for display."""
    if default is None:
        return "-"
    if isinstance(default, bool):
        return str(default).lower()
    if isinstance(default, str) and default == "":
        return '""'
    return str(default)


def _get_click_command(command_path: str) -> click.Command | None:
    """Get a Click command from a path like 'transcribe' or 'memory.proxy'."""
    parts = command_path.split(".")
    click_app = get_command(app)

    cmd: click.Command | click.Group = click_app
    for part in parts:
        if isinstance(cmd, click.Group):
            cmd = cmd.commands.get(part)  # type: ignore[assignment]
            if cmd is None:
                return None
        else:
            return None
    return cmd


def _extract_options_from_click(cmd: click.Command) -> list[dict[str, Any]]:
    """Extract options from a Click command."""
    options = []
    for param in cmd.params:
        if isinstance(param, click.Option):
            # Get long and short option names
            long_opts = [n for n in param.opts if n.startswith("--")]
            short_opts = [n for n in param.opts if n.startswith("-") and not n.startswith("--")]

            # Build display name: prefer long form, include short if available
            if long_opts:
                primary_name = max(long_opts, key=len)
                # Include short flag if available (e.g., "--from", "-f" -> "--from, -f")
                if short_opts:
                    primary_name = f"{primary_name}, {short_opts[0]}"
            elif short_opts:
                primary_name = short_opts[0]
            else:
                primary_name = f"--{param.name}"

            # Handle boolean flags with --foo/--no-foo pattern
            if param.is_flag and param.secondary_opts:
                # e.g., --llm/--no-llm
                base_opt = long_opts[0] if long_opts else param.opts[0]
                primary_name = f"{base_opt}/{param.secondary_opts[0]}"

            # Get panel from rich_help_panel or use default
            panel = getattr(param, "rich_help_panel", None) or "Options"

            options.append(
                {
                    "name": primary_name,
                    "type": param.type.name.upper() if hasattr(param.type, "name") else "TEXT",
                    "default": _format_default(param.default),
                    "help": param.help or "",
                    "panel": panel,
                    "envvar": param.envvar[0] if param.envvar else None,
                    "required": param.required,
                    "is_flag": param.is_flag,
                },
            )
    return options


def _get_command_options(command_path: str) -> list[dict[str, Any]]:
    """Extract all options from a Typer command."""
    cmd = _get_click_command(command_path)
    if cmd is None:
        return []
    return _extract_options_from_click(cmd)


def _options_table(
    command_path: str,
    panel: str | None = None,
    *,
    include_type: bool = True,
    include_default: bool = True,
) -> str:
    """Generate a Markdown table of options for a command."""
    options = _get_command_options(command_path)
    if panel:
        options = [o for o in options if o["panel"] == panel]

    if not options:
        return f"*No options found for panel '{panel}'*" if panel else "*No options found*"

    # Build header
    header_parts = ["Option"]
    if include_type:
        header_parts.append("Type")
    if include_default:
        header_parts.append("Default")
    header_parts.append("Description")

    header = "| " + " | ".join(header_parts) + " |"
    separator = "|" + "|".join("-" * (len(p) + 2) for p in header_parts) + "|"

    lines = [header, separator]

    for opt in options:
        row_parts = [f"`{opt['name']}`"]
        if include_type:
            row_parts.append(opt["type"])
        if include_default:
            default = opt["default"]
            row_parts.append(f"`{default}`" if default != "-" else "-")
        row_parts.append(opt["help"])
        lines.append("| " + " | ".join(row_parts) + " |")

    return "\n".join(lines)


def _options_by_panel(
    command_path: str,
    *,
    include_type: bool = True,
    include_default: bool = True,
    heading_level: int = 3,
) -> str:
    """Generate options tables grouped by panel."""
    options = _get_command_options(command_path)
    if not options:
        return "*No options found*"

    # Get unique panels in order of first appearance
    panels: list[str] = []
    for opt in options:
        if opt["panel"] not in panels:
            panels.append(opt["panel"])

    heading_prefix = "#" * heading_level
    output = []

    for panel in panels:
        output.append(f"{heading_prefix} {panel}\n")
        output.append(
            _options_table(
                command_path,
                panel=panel,
                include_type=include_type,
                include_default=include_default,
            ),
        )
        output.append("")  # Blank line between panels

    return "\n".join(output)


def _list_commands() -> list[str]:
    """List all available commands including subcommands."""
    click_app = get_command(app)
    commands = []

    def _walk(cmd: click.Command | click.Group, prefix: str = "") -> None:
        if isinstance(cmd, click.Group):
            for name, subcmd in cmd.commands.items():
                path = f"{prefix}.{name}" if prefix else name
                if isinstance(subcmd, click.Group):
                    _walk(subcmd, path)
                else:
                    commands.append(path)
        elif prefix:
            commands.append(prefix)

    _walk(click_app)
    return sorted(commands)


def env_vars_table() -> str:
    """Generate a table of all environment variables.

    Returns:
        Markdown table of environment variables and descriptions

    """
    lines = [
        "| Variable | Description |",
        "|----------|-------------|",
    ]

    seen = set()
    for name in dir(opts):
        if name.startswith("_"):
            continue
        obj = getattr(opts, name)
        if hasattr(obj, "envvar") and obj.envvar:
            envvar = obj.envvar
            if envvar not in seen:
                seen.add(envvar)
                help_text = getattr(obj, "help", "") or ""
                lines.append(f"| `{envvar}` | {help_text} |")

    return "\n".join(lines)


def provider_matrix() -> str:
    """Generate provider comparison matrix.

    Returns:
        Markdown table comparing local vs cloud providers

    """
    return """| Capability | Local (Default) | Cloud Options |
|------------|-----------------|---------------|
| **LLM** | Ollama (`ollama`) | OpenAI (`openai`), Gemini (`gemini`) |
| **ASR** (Speech-to-Text) | Wyoming/Faster Whisper (`wyoming`) | OpenAI-compatible Whisper (`openai`), Gemini (`gemini`) |
| **TTS** (Text-to-Speech) | Wyoming/Piper (`wyoming`), Kokoro (`kokoro`) | OpenAI-compatible TTS (`openai`) |
| **Wake Word** | Wyoming/openWakeWord | - |"""


def commands_table(
    category: str | None = None,
    link_prefix: str = "",
) -> str:
    """Generate a table of available commands.

    Args:
        category: Filter by category (voice, text, ai, install, config) or None for all
        link_prefix: Prefix for links (e.g., "docs/commands/" for README.md)

    Returns:
        Markdown table of commands

    """
    # Define command metadata
    command_info = {
        "transcribe": ("Speech-to-text", "Record voice → text in clipboard", "voice"),
        "transcribe-daemon": ("Continuous transcription", "Background VAD service", "voice"),
        "speak": ("Text-to-speech", "Read text aloud", "voice"),
        "voice-edit": ("Voice-powered editor", "Edit clipboard with voice", "voice"),
        "assistant": ("Wake word assistant", "Hands-free voice interaction", "voice"),
        "chat": ("Conversational AI", "Voice chat with tools", "voice"),
        "autocorrect": ("Grammar & spelling", "Fix text from clipboard", "text"),
        "rag-proxy": ("RAG server", "Chat with documents", "ai"),
        "memory.proxy": ("Long-term memory", "Persistent conversation memory", "ai"),
        "memory.add": ("Add memories", "Directly add facts to memory", "ai"),
        "server": ("Transcription server", "HTTP API for transcription", "ai"),
        "install-services": ("Install services", "Set up AI services", "install"),
        "install-hotkeys": ("Install hotkeys", "Set up system hotkeys", "install"),
        "start-services": ("Start services", "Launch all services", "install"),
        "config": ("Configuration", "Manage config files", "config"),
    }

    if category:
        commands = {k: v for k, v in command_info.items() if v[2] == category}
    else:
        commands = command_info

    if not commands:
        return "*No commands found*"

    lines = [
        "| Command | Purpose | Use Case |",
        "|---------|---------|----------|",
    ]

    for cmd, (purpose, use_case, _) in commands.items():
        # Convert command path to link
        doc_path = cmd.replace(".", "/")
        link = f"{link_prefix}{doc_path}.md"
        lines.append(f"| [`{cmd}`]({link}) | {purpose} | {use_case} |")

    return "\n".join(lines)


def config_example(command_path: str | None = None) -> str:
    """Generate example TOML configuration for a command.

    Args:
        command_path: Command path or None for defaults section

    Returns:
        TOML configuration snippet

    """
    if command_path is None:
        # Generate defaults section
        return """[defaults]
# Provider defaults (can be overridden per command)
# llm_provider = "ollama"
# asr_provider = "wyoming"
# tts_provider = "wyoming"

# API keys (or use environment variables)
# openai_api_key = "sk-..."
# gemini_api_key = "..."

# Audio devices
# input_device_index = 1
# output_device_index = 0"""

    options = _get_command_options(command_path)
    if not options:
        return f"# No configurable options for {command_path}"

    section = command_path.replace(".", "-")
    lines = [f"[{section}]"]

    for opt in options:
        # Skip process management and meta options
        if opt["panel"] in ("Process Management Options",):
            continue

        # Convert flag name to config key
        key = opt["name"].lstrip("-").replace("-", "_").split("/")[0]
        default = opt["default"]
        help_text = opt["help"]

        # Format the value appropriately
        if default == "-":
            value = '""' if opt["type"] == "TEXT" else "null"
            lines.append(f"# {key} = {value}  # {help_text}")
        elif opt["type"] == "TEXT":
            lines.append(f'# {key} = "{default}"  # {help_text}')
        elif opt["type"] in ("INTEGER", "FLOAT") or opt["is_flag"]:
            lines.append(f"# {key} = {default}  # {help_text}")
        else:
            lines.append(f"# {key} = {default}  # {help_text}")

    return "\n".join(lines)


def all_options_for_docs(command_path: str) -> str:
    """Generate complete options documentation for a command page.

    This is the main function to use in docs/commands/*.md files.
    It generates all options grouped by panel with proper formatting.

    Args:
        command_path: Command path like "transcribe" or "memory.proxy"

    Returns:
        Complete Markdown options section

    """
    return _options_by_panel(
        command_path,
        include_type=False,  # Types are often obvious and clutter the table
        include_default=True,
        heading_level=3,
    )


def extras_table() -> str:
    """Generate a table of available extras for install-extras command."""
    lines = [
        "| Extra | Description |",
        "|-------|-------------|",
    ]
    for name, description in EXTRAS.items():
        lines.append(f"| `{name}` | {description} |")
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo: print options for transcribe command
    print("=== Available Commands ===")
    for cmd in _list_commands():
        print(f"  {cmd}")
    print()

    print("=== transcribe options by panel ===")
    print(_options_by_panel("transcribe"))

    print("\n=== Environment Variables ===")
    print(env_vars_table())

    print("\n=== Provider Matrix ===")
    print(provider_matrix())
