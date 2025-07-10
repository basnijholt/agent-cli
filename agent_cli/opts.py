"""Shared Typer options for the Agent CLI agents."""

from pathlib import Path

import typer

# --- Provider Selection ---
LLM_PROVIDER: str = typer.Option(
    "local",
    "--llm-provider",
    help="The LLM provider to use ('local' for Ollama, 'openai').",
    rich_help_panel="Provider Selection",
)
ASR_PROVIDER: str = typer.Option(
    "local",
    "--asr-provider",
    help="The ASR provider to use ('local' for Wyoming, 'openai').",
    rich_help_panel="Provider Selection",
)
TTS_PROVIDER: str = typer.Option(
    "local",
    "--tts-provider",
    help="The TTS provider to use ('local' for Wyoming, 'openai', 'kokoro').",
    rich_help_panel="Provider Selection",
)


# --- LLM Configuration ---
# Ollama (local service)
OLLAMA_MODEL: str = typer.Option(
    "qwen3:4b",
    "--ollama-model",
    help="The Ollama model to use. Default is qwen3:4b.",
    rich_help_panel="LLM Configuration: Ollama (local)",
)
OLLAMA_HOST: str = typer.Option(
    "http://localhost:11434",
    "--ollama-host",
    help="The Ollama server host. Default is http://localhost:11434.",
    rich_help_panel="LLM Configuration: Ollama (local)",
)
# OpenAI
OPENAI_LLM_MODEL: str = typer.Option(
    "gpt-4o-mini",
    "--openai-llm-model",
    help="The OpenAI model to use for LLM tasks.",
    rich_help_panel="LLM Configuration: OpenAI",
)
OPENAI_API_KEY: str | None = typer.Option(
    None,
    "--openai-api-key",
    help="Your OpenAI API key. Can also be set with the OPENAI_API_KEY environment variable.",
    envvar="OPENAI_API_KEY",
    rich_help_panel="LLM Configuration: OpenAI",
)
LLM: bool = typer.Option(
    False,  # noqa: FBT003
    "--llm/--no-llm",
    help="Use an LLM to process the transcript.",
    rich_help_panel="LLM Configuration",
)


# --- ASR (Audio) Configuration ---
# General ASR
INPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--input-device-index",
    help="Index of the PyAudio input device to use.",
    rich_help_panel="ASR (Audio) Configuration",
)
INPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--input-device-name",
    help="Device name keywords for partial matching.",
    rich_help_panel="ASR (Audio) Configuration",
)
LIST_DEVICES: bool = typer.Option(
    False,  # noqa: FBT003
    "--list-devices",
    help="List available audio input and output devices and exit.",
    is_eager=True,
    rich_help_panel="ASR (Audio) Configuration",
)
# Wyoming (local service)
WYOMING_ASR_SERVER_IP: str = typer.Option(
    "localhost",
    "--wyoming-asr-ip",
    help="Wyoming ASR server IP address.",
    rich_help_panel="ASR (Audio) Configuration: Wyoming (local)",
)
WYOMING_ASR_SERVER_PORT: int = typer.Option(
    10300,
    "--wyoming-asr-port",
    help="Wyoming ASR server port.",
    rich_help_panel="ASR (Audio) Configuration: Wyoming (local)",
)
# OpenAI
OPENAI_ASR_MODEL: str = typer.Option(
    "whisper-1",
    "--openai-asr-model",
    help="The OpenAI model to use for ASR (transcription).",
    rich_help_panel="ASR (Audio) Configuration: OpenAI",
)


# --- Wake Word Options ---
WAKE_WORD_SERVER_IP: str = typer.Option(
    "localhost",
    "--wake-server-ip",
    help="Wyoming wake word server IP address.",
    rich_help_panel="Wake Word Options",
)
WAKE_WORD_SERVER_PORT: int = typer.Option(
    10400,
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


# --- TTS (Text-to-Speech) Configuration ---
# General TTS
ENABLE_TTS: bool = typer.Option(
    False,  # noqa: FBT003
    "--tts/--no-tts",
    help="Enable text-to-speech for responses.",
    rich_help_panel="TTS (Text-to-Speech) Configuration",
)
TTS_SPEED: float = typer.Option(
    1.0,
    "--tts-speed",
    help="Speech speed multiplier (1.0 = normal, 2.0 = twice as fast, 0.5 = half speed).",
    rich_help_panel="TTS (Text-to-Speech) Configuration",
)
OUTPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--output-device-index",
    help="Index of the PyAudio output device to use for TTS.",
    rich_help_panel="TTS (Text-to-Speech) Configuration",
)
OUTPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--output-device-name",
    help="Output device name keywords for partial matching.",
    rich_help_panel="TTS (Text-to-Speech) Configuration",
)
# Wyoming (local service)
WYOMING_TTS_SERVER_IP: str = typer.Option(
    "localhost",
    "--wyoming-tts-ip",
    help="Wyoming TTS server IP address.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Wyoming (local)",
)
WYOMING_TTS_SERVER_PORT: int = typer.Option(
    10200,
    "--wyoming-tts-port",
    help="Wyoming TTS server port.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Wyoming (local)",
)
WYOMING_VOICE_NAME: str | None = typer.Option(
    None,
    "--wyoming-voice",
    help="Voice name to use for Wyoming TTS (e.g., 'en_US-lessac-medium').",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Wyoming (local)",
)
WYOMING_TTS_LANGUAGE: str | None = typer.Option(
    None,
    "--wyoming-tts-language",
    help="Language for Wyoming TTS (e.g., 'en_US').",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Wyoming (local)",
)
WYOMING_SPEAKER: str | None = typer.Option(
    None,
    "--wyoming-speaker",
    help="Speaker name for Wyoming TTS voice.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Wyoming (local)",
)
# OpenAI
OPENAI_TTS_MODEL: str = typer.Option(
    "tts-1",
    "--openai-tts-model",
    help="The OpenAI model to use for TTS.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: OpenAI",
)
OPENAI_TTS_VOICE: str = typer.Option(
    "alloy",
    "--openai-tts-voice",
    help="The voice to use for OpenAI TTS.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: OpenAI",
)


# Kokoro
KOKORO_TTS_MODEL: str = typer.Option(
    "kokoro",
    "--kokoro-tts-model",
    help="The Kokoro model to use for TTS.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Kokoro",
)
KOKORO_TTS_VOICE: str = typer.Option(
    "af_sky",
    "--kokoro-tts-voice",
    help="The voice to use for Kokoro TTS.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Kokoro",
)
KOKORO_TTS_HOST: str = typer.Option(
    "http://localhost:8880/v1",
    "--kokoro-tts-host",
    help="The base URL for the Kokoro API.",
    rich_help_panel="TTS (Text-to-Speech) Configuration: Kokoro",
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
