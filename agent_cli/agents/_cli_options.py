"""Shared Typer options for the Agent CLI agents."""

from pathlib import Path

import typer

from agent_cli import config

# --- LLM Options ---
MODEL: str = typer.Option(
    config.DEFAULT_MODEL,
    "--model",
    "-m",
    help=f"The Ollama model to use. Default is {config.DEFAULT_MODEL}.",
    rich_help_panel="LLM Options",
)
OLLAMA_HOST: str = typer.Option(
    config.OLLAMA_HOST,
    "--ollama-host",
    help=f"The Ollama server host. Default is {config.OLLAMA_HOST}.",
    rich_help_panel="LLM Options",
)
LLM: bool = typer.Option(
    False,  # noqa: FBT003
    "--llm/--no-llm",
    help="Use an LLM to process the transcript.",
    rich_help_panel="LLM Options",
)


# --- ASR (Audio) Options ---
DEVICE_INDEX: int | None = typer.Option(
    None,
    "--input-device-index",
    help="Index of the PyAudio input device to use.",
    rich_help_panel="ASR (Audio) Options",
)
DEVICE_NAME: str | None = typer.Option(
    None,
    "--input-device-name",
    help="Device name keywords for partial matching. Supports comma-separated list where each term can partially match device names (case-insensitive). First matching device is selected.",
    rich_help_panel="ASR (Audio) Options",
)
LIST_DEVICES: bool = typer.Option(
    False,  # noqa: FBT003
    "--list-devices",
    help="List available audio input and output devices and exit.",
    is_eager=True,
    rich_help_panel="ASR (Audio) Options",
)
ASR_SERVER_IP: str = typer.Option(
    config.ASR_SERVER_IP,
    "--asr-server-ip",
    help="Wyoming ASR server IP address.",
    rich_help_panel="ASR (Audio) Options",
)
ASR_SERVER_PORT: int = typer.Option(
    config.ASR_SERVER_PORT,
    "--asr-server-port",
    help="Wyoming ASR server port.",
    rich_help_panel="ASR (Audio) Options",
)


# --- Wake Word Options ---
WAKE_WORD_SERVER_IP: str = typer.Option(
    config.WAKE_WORD_SERVER_IP,
    "--wake-server-ip",
    help="Wyoming wake word server IP address.",
    rich_help_panel="Wake Word Options",
)
WAKE_WORD_SERVER_PORT: int = typer.Option(
    config.WAKE_WORD_SERVER_PORT,
    "--wake-server-port",
    help="Wyoming wake word server port.",
    rich_help_panel="Wake Word Options",
)
WAKE_WORD_NAME: str = typer.Option(
    "ok_nabu",
    "--wake-word",
    help="Name of wake word to detect (e.g., 'ok_nabu', 'hey_jarvis').",
    rich_help_panel="Wake Word Options",
)


# --- TTS (Text-to-Speech) Options ---
TTS_SERVER_IP: str = typer.Option(
    config.TTS_SERVER_IP,
    "--tts-server-ip",
    help="Wyoming TTS server IP address.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
TTS_SERVER_PORT: int = typer.Option(
    config.TTS_SERVER_PORT,
    "--tts-server-port",
    help="Wyoming TTS server port.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
VOICE_NAME: str | None = typer.Option(
    None,
    "--voice",
    help="Voice name to use for TTS (e.g., 'en_US-lessac-medium').",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
TTS_LANGUAGE: str | None = typer.Option(
    None,
    "--tts-language",
    help="Language for TTS (e.g., 'en_US').",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
SPEAKER: str | None = typer.Option(
    None,
    "--speaker",
    help="Speaker name for TTS voice.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
OUTPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--output-device-index",
    help="Index of the PyAudio output device to use for TTS.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
OUTPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--output-device-name",
    help="Output device name keywords for partial matching. Supports comma-separated list where each term can partially match device names (case-insensitive). First matching device is selected.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
ENABLE_TTS: bool = typer.Option(
    False,  # noqa: FBT003
    "--tts/--no-tts",
    help="Enable text-to-speech for responses.",
    rich_help_panel="TTS (Text-to-Speech) Options",
)
TTS_SPEED: float = typer.Option(
    1.0,
    "--tts-speed",
    help="Speech speed multiplier (1.0 = normal, 2.0 = twice as fast, 0.5 = half speed).",
    rich_help_panel="TTS (Text-to-Speech) Options",
)


# --- Process Management Options ---
STOP: bool = typer.Option(
    False,  # noqa: FBT003
    "--stop",
    help="Stop any running background process.",
    rich_help_panel="Process Management Options",
)
STATUS: bool = typer.Option(
    False,  # noqa: FBT003
    "--status",
    help="Check if a background process is running.",
    rich_help_panel="Process Management Options",
)
TOGGLE: bool = typer.Option(
    False,  # noqa: FBT003
    "--toggle",
    help="Toggle the background process on/off. "
    "If the process is running, it will be stopped. "
    "If the process is not running, it will be started.",
    rich_help_panel="Process Management Options",
)

# --- General Options ---


def _conf_callback(ctx: typer.Context, param: typer.CallbackParam, value: str) -> str:  # noqa: ARG001
    from agent_cli.cli import set_config_defaults  # noqa: PLC0415

    set_config_defaults(ctx, value)
    return value


CONFIG_FILE: str | None = typer.Option(
    None,
    "--config",
    help="Path to a TOML configuration file.",
    is_eager=True,
    callback=_conf_callback,
    rich_help_panel="General Options",
)
CLIPBOARD: bool = typer.Option(
    True,  # noqa: FBT003
    "--clipboard/--no-clipboard",
    help="Copy result to clipboard.",
    rich_help_panel="General Options",
)
LOG_LEVEL: str = typer.Option(
    "WARNING",
    "--log-level",
    help="Set logging level.",
    case_sensitive=False,
    rich_help_panel="General Options",
)
LOG_FILE: str | None = typer.Option(
    None,
    "--log-file",
    help="Path to a file to write logs to.",
    rich_help_panel="General Options",
)
QUIET: bool = typer.Option(
    False,  # noqa: FBT003
    "-q",
    "--quiet",
    help="Suppress console output from rich.",
    rich_help_panel="General Options",
)
SAVE_FILE: Path | None = typer.Option(
    None,
    "--save-file",
    help="Save TTS response audio to WAV file.",
    rich_help_panel="General Options",
)
