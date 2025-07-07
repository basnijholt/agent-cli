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
)
OLLAMA_HOST: str = typer.Option(
    config.OLLAMA_HOST,
    "--ollama-host",
    help=f"The Ollama server host. Default is {config.OLLAMA_HOST}.",
)
LLM: bool = typer.Option(
    False,  # noqa: FBT003
    "--llm/--no-llm",
    help="Use an LLM to process the transcript.",
)


# --- ASR (Audio) Options ---
DEVICE_INDEX: int | None = typer.Option(
    None,
    "--input-device-index",
    help="Index of the PyAudio input device to use.",
)
DEVICE_NAME: str | None = typer.Option(
    None,
    "--input-device-name",
    help="Device name keywords for partial matching. Supports comma-separated list where each term can partially match device names (case-insensitive). First matching device is selected.",
)
LIST_DEVICES: bool = typer.Option(
    False,  # noqa: FBT003
    "--list-input-devices",
    help="List available audio input devices and exit.",
    is_eager=True,
)
ASR_SERVER_IP: str = typer.Option(
    config.ASR_SERVER_IP,
    "--asr-server-ip",
    help="Wyoming ASR server IP address.",
)
ASR_SERVER_PORT: int = typer.Option(
    config.ASR_SERVER_PORT,
    "--asr-server-port",
    help="Wyoming ASR server port.",
)


# --- Wake Word Options ---
WAKE_WORD_SERVER_IP: str = typer.Option(
    config.WAKE_WORD_SERVER_IP,
    "--wake-server-ip",
    help="Wyoming wake word server IP address.",
)
WAKE_WORD_SERVER_PORT: int = typer.Option(
    config.WAKE_WORD_SERVER_PORT,
    "--wake-server-port",
    help="Wyoming wake word server port.",
)
WAKE_WORD_NAME: str = typer.Option(
    "ok_nabu",
    "--wake-word",
    help="Name of wake word to detect (e.g., 'ok_nabu', 'hey_jarvis').",
)


# --- TTS (Text-to-Speech) Options ---
TTS_SERVER_IP: str = typer.Option(
    config.TTS_SERVER_IP,
    "--tts-server-ip",
    help="Wyoming TTS server IP address.",
)
TTS_SERVER_PORT: int = typer.Option(
    config.TTS_SERVER_PORT,
    "--tts-server-port",
    help="Wyoming TTS server port.",
)
VOICE_NAME: str | None = typer.Option(
    None,
    "--voice",
    help="Voice name to use for TTS (e.g., 'en_US-lessac-medium').",
)
TTS_LANGUAGE: str | None = typer.Option(
    None,
    "--tts-language",
    help="Language for TTS (e.g., 'en_US').",
)
SPEAKER: str | None = typer.Option(
    None,
    "--speaker",
    help="Speaker name for TTS voice.",
)
OUTPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--output-device-index",
    help="Index of the PyAudio output device to use for TTS.",
)
OUTPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--output-device-name",
    help="Output device name keywords for partial matching. Supports comma-separated list where each term can partially match device names (case-insensitive). First matching device is selected.",
)
LIST_OUTPUT_DEVICES: bool = typer.Option(
    False,  # noqa: FBT003
    "--list-output-devices",
    help="List available audio output devices and exit.",
    is_eager=True,
)
ENABLE_TTS: bool = typer.Option(
    False,  # noqa: FBT003
    "--tts/--no-tts",
    help="Enable text-to-speech for responses.",
)
TTS_SPEED: float = typer.Option(
    1.0,
    "--tts-speed",
    help="Speech speed multiplier (1.0 = normal, 2.0 = twice as fast, 0.5 = half speed).",
)


# --- Process Management Options ---
STOP: bool = typer.Option(
    False,  # noqa: FBT003
    "--stop",
    help="Stop any running background process.",
)
STATUS: bool = typer.Option(
    False,  # noqa: FBT003
    "--status",
    help="Check if a background process is running.",
)
TOGGLE: bool = typer.Option(
    False,  # noqa: FBT003
    "--toggle",
    help="Toggle the background process on/off. "
    "If the process is running, it will be stopped. "
    "If the process is not running, it will be started.",
)

# --- General Options ---


def _conf_callback(ctx: typer.Context, param: typer.CallbackParam, value: str) -> str:  # noqa: ARG001
    from agent_cli.cli import set_config_defaults

    set_config_defaults(ctx, value)
    return value


CONFIG_FILE: str | None = typer.Option(
    None,
    "--config",
    help="Path to a TOML configuration file.",
    is_eager=True,
    callback=_conf_callback,
)
CLIPBOARD: bool = typer.Option(
    True,  # noqa: FBT003
    "--clipboard/--no-clipboard",
    help="Copy result to clipboard.",
)
LOG_LEVEL: str = typer.Option(
    "WARNING",
    "--log-level",
    help="Set logging level.",
    case_sensitive=False,
)
LOG_FILE: str | None = typer.Option(
    None,
    "--log-file",
    help="Path to a file to write logs to.",
)
QUIET: bool = typer.Option(
    False,  # noqa: FBT003
    "-q",
    "--quiet",
    help="Suppress console output from rich.",
)
SAVE_FILE: Path | None = typer.Option(
    None,
    "--save-file",
    help="Save TTS response audio to WAV file.",
)
