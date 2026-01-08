"""Shared Typer options for the Agent CLI agents."""

import copy
from pathlib import Path

import typer
from typer.models import OptionInfo

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL, DEFAULT_OPENAI_MODEL


def with_default(option: OptionInfo, default: str) -> OptionInfo:
    """Create a copy of a typer Option with a different default value."""
    opt = copy.copy(option)
    opt.default = default
    return opt


# --- Provider Selection ---
LLM_PROVIDER: str = typer.Option(
    "ollama",
    "--llm-provider",
    help="The LLM provider to use ('ollama', 'openai', 'gemini').",
    rich_help_panel="Provider Selection",
)
ASR_PROVIDER: str = typer.Option(
    "wyoming",
    "--asr-provider",
    help="The ASR provider to use ('wyoming', 'openai', 'gemini').",
    rich_help_panel="Provider Selection",
)
TTS_PROVIDER: str = typer.Option(
    "wyoming",
    "--tts-provider",
    help="The TTS provider to use ('wyoming', 'openai', 'kokoro', 'gemini').",
    rich_help_panel="Provider Selection",
)


# --- LLM Configuration ---
LLM: bool = typer.Option(
    False,  # noqa: FBT003
    "--llm/--no-llm",
    help="Use an LLM to process the transcript.",
    rich_help_panel="LLM Configuration",
)
# Ollama (local service)
LLM_OLLAMA_MODEL: str = typer.Option(
    "gemma3:4b",
    "--llm-ollama-model",
    help="The Ollama model to use. Default is gemma3:4b.",
    rich_help_panel="LLM: Ollama",
)
LLM_OLLAMA_HOST: str = typer.Option(
    "http://localhost:11434",
    "--llm-ollama-host",
    help="The Ollama server host. Default is http://localhost:11434.",
    rich_help_panel="LLM: Ollama",
)
# OpenAI
LLM_OPENAI_MODEL: str = typer.Option(
    DEFAULT_OPENAI_MODEL,
    "--llm-openai-model",
    help="The OpenAI model to use for LLM tasks.",
    rich_help_panel="LLM: OpenAI-compatible",
)
OPENAI_API_KEY: str | None = typer.Option(
    None,
    "--openai-api-key",
    help="Your OpenAI API key. Can also be set with the OPENAI_API_KEY environment variable.",
    envvar="OPENAI_API_KEY",
    rich_help_panel="LLM: OpenAI-compatible",
)
OPENAI_BASE_URL: str | None = typer.Option(
    None,
    "--openai-base-url",
    help="Custom base URL for OpenAI-compatible API (e.g., for llama-server: http://localhost:8080/v1).",
    envvar="OPENAI_BASE_URL",
    rich_help_panel="LLM: OpenAI-compatible",
)
# Gemini
LLM_GEMINI_MODEL: str = typer.Option(
    "gemini-3-flash-preview",
    "--llm-gemini-model",
    help="The Gemini model to use for LLM tasks.",
    rich_help_panel="LLM: Gemini",
)
GEMINI_API_KEY: str | None = typer.Option(
    None,
    "--gemini-api-key",
    help="Your Gemini API key. Can also be set with the GEMINI_API_KEY environment variable.",
    envvar="GEMINI_API_KEY",
    rich_help_panel="LLM: Gemini",
)
EMBEDDING_MODEL: str = typer.Option(
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    "--embedding-model",
    help="Embedding model to use for vectorization.",
    rich_help_panel="LLM Configuration",
)

# --- ASR (Audio) Configuration ---
# General ASR
INPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--input-device-index",
    help="Index of the audio input device to use.",
    rich_help_panel="Audio Input",
)
INPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--input-device-name",
    help="Device name keywords for partial matching.",
    rich_help_panel="Audio Input",
)
LIST_DEVICES: bool = typer.Option(
    False,  # noqa: FBT003
    "--list-devices",
    help="List available audio input and output devices and exit.",
    is_eager=True,
    rich_help_panel="Audio Input",
)
# Wyoming (local service)
ASR_WYOMING_IP: str = typer.Option(
    "localhost",
    "--asr-wyoming-ip",
    help="Wyoming ASR server IP address.",
    rich_help_panel="Audio Input: Wyoming",
)
ASR_WYOMING_PORT: int = typer.Option(
    10300,
    "--asr-wyoming-port",
    help="Wyoming ASR server port.",
    rich_help_panel="Audio Input: Wyoming",
)
# OpenAI
ASR_OPENAI_MODEL: str = typer.Option(
    "whisper-1",
    "--asr-openai-model",
    help="The OpenAI model to use for ASR (transcription).",
    rich_help_panel="Audio Input: OpenAI-compatible",
)
ASR_OPENAI_BASE_URL: str | None = typer.Option(
    None,
    "--asr-openai-base-url",
    help="Custom base URL for OpenAI-compatible ASR API (e.g., for custom Whisper server: http://localhost:9898).",
    rich_help_panel="Audio Input: OpenAI-compatible",
)
ASR_OPENAI_PROMPT: str | None = typer.Option(
    None,
    "--asr-openai-prompt",
    help="Custom prompt to guide transcription (optional).",
    rich_help_panel="Audio Input: OpenAI-compatible",
)
# Gemini ASR
ASR_GEMINI_MODEL: str = typer.Option(
    "gemini-3-flash-preview",
    "--asr-gemini-model",
    help="The Gemini model to use for ASR (transcription).",
    rich_help_panel="Audio Input: Gemini",
)


# --- Wake Word Options ---
WAKE_SERVER_IP: str = typer.Option(
    "localhost",
    "--wake-server-ip",
    help="Wyoming wake word server IP address.",
    rich_help_panel="Wake Word",
)
WAKE_SERVER_PORT: int = typer.Option(
    10400,
    "--wake-server-port",
    help="Wyoming wake word server port.",
    rich_help_panel="Wake Word",
)
WAKE_WORD: str = typer.Option(
    "ok_nabu",
    "--wake-word",
    help="Name of wake word to detect (e.g., 'ok_nabu', 'hey_jarvis').",
    rich_help_panel="Wake Word",
)


# --- TTS (Text-to-Speech) Configuration ---
# General TTS
ENABLE_TTS: bool = typer.Option(
    False,  # noqa: FBT003
    "--tts/--no-tts",
    help="Enable text-to-speech for responses.",
    rich_help_panel="Audio Output",
)
TTS_SPEED: float = typer.Option(
    1.0,
    "--tts-speed",
    help="Speech speed multiplier (1.0 = normal, 2.0 = twice as fast, 0.5 = half speed).",
    rich_help_panel="Audio Output",
)
OUTPUT_DEVICE_INDEX: int | None = typer.Option(
    None,
    "--output-device-index",
    help="Index of the audio output device to use for TTS.",
    rich_help_panel="Audio Output",
)
OUTPUT_DEVICE_NAME: str | None = typer.Option(
    None,
    "--output-device-name",
    help="Output device name keywords for partial matching.",
    rich_help_panel="Audio Output",
)
# Wyoming (local service)
TTS_WYOMING_IP: str = typer.Option(
    "localhost",
    "--tts-wyoming-ip",
    help="Wyoming TTS server IP address.",
    rich_help_panel="Audio Output: Wyoming",
)
TTS_WYOMING_PORT: int = typer.Option(
    10200,
    "--tts-wyoming-port",
    help="Wyoming TTS server port.",
    rich_help_panel="Audio Output: Wyoming",
)
TTS_WYOMING_VOICE: str | None = typer.Option(
    None,
    "--tts-wyoming-voice",
    help="Voice name to use for Wyoming TTS (e.g., 'en_US-lessac-medium').",
    rich_help_panel="Audio Output: Wyoming",
)
TTS_WYOMING_LANGUAGE: str | None = typer.Option(
    None,
    "--tts-wyoming-language",
    help="Language for Wyoming TTS (e.g., 'en_US').",
    rich_help_panel="Audio Output: Wyoming",
)
TTS_WYOMING_SPEAKER: str | None = typer.Option(
    None,
    "--tts-wyoming-speaker",
    help="Speaker name for Wyoming TTS voice.",
    rich_help_panel="Audio Output: Wyoming",
)
# OpenAI
TTS_OPENAI_MODEL: str = typer.Option(
    "tts-1",
    "--tts-openai-model",
    help="The OpenAI model to use for TTS.",
    rich_help_panel="Audio Output: OpenAI-compatible",
)
TTS_OPENAI_VOICE: str = typer.Option(
    "alloy",
    "--tts-openai-voice",
    help="The voice to use for OpenAI-compatible TTS.",
    rich_help_panel="Audio Output: OpenAI-compatible",
)
TTS_OPENAI_BASE_URL: str | None = typer.Option(
    None,
    "--tts-openai-base-url",
    help="Custom base URL for OpenAI-compatible TTS API (e.g., http://localhost:8000/v1 for a proxy).",
    rich_help_panel="Audio Output: OpenAI-compatible",
)


# Kokoro
TTS_KOKORO_MODEL: str = typer.Option(
    "kokoro",
    "--tts-kokoro-model",
    help="The Kokoro model to use for TTS.",
    rich_help_panel="Audio Output: Kokoro",
)
TTS_KOKORO_VOICE: str = typer.Option(
    "af_sky",
    "--tts-kokoro-voice",
    help="The voice to use for Kokoro TTS.",
    rich_help_panel="Audio Output: Kokoro",
)
TTS_KOKORO_HOST: str = typer.Option(
    "http://localhost:8880/v1",
    "--tts-kokoro-host",
    help="The base URL for the Kokoro API.",
    rich_help_panel="Audio Output: Kokoro",
)

# Gemini TTS
TTS_GEMINI_MODEL: str = typer.Option(
    "gemini-2.5-flash-preview-tts",
    "--tts-gemini-model",
    help="The Gemini model to use for TTS.",
    rich_help_panel="Audio Output: Gemini",
)
TTS_GEMINI_VOICE: str = typer.Option(
    "Kore",
    "--tts-gemini-voice",
    help="The voice to use for Gemini TTS (e.g., 'Kore', 'Puck', 'Charon', 'Fenrir').",
    rich_help_panel="Audio Output: Gemini",
)


# --- Process Management Options ---
STOP: bool = typer.Option(
    False,  # noqa: FBT003
    "--stop",
    help="Stop any running background process.",
    rich_help_panel="Process Management",
)
STATUS: bool = typer.Option(
    False,  # noqa: FBT003
    "--status",
    help="Check if a background process is running.",
    rich_help_panel="Process Management",
)
TOGGLE: bool = typer.Option(
    False,  # noqa: FBT003
    "--toggle",
    help="Toggle the background process on/off. "
    "If the process is running, it will be stopped. "
    "If the process is not running, it will be started.",
    rich_help_panel="Process Management",
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
PRINT_ARGS: bool = typer.Option(
    False,  # noqa: FBT003
    "--print-args",
    help="Print the command line arguments, including variables taken from the configuration file.",
    is_eager=True,
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
TRANSCRIPTION_LOG: Path | None = typer.Option(
    None,
    "--transcription-log",
    help="Path to log transcription results with timestamps, hostname, model, and raw output.",
    rich_help_panel="General Options",
)

# --- Server Options ---
SERVER_HOST: str = typer.Option(
    "0.0.0.0",  # noqa: S104
    "--host",
    help="Host/IP to bind API servers to.",
    rich_help_panel="Server Configuration",
)

# --- Transcribe Specific Options ---
FROM_FILE: Path | None = typer.Option(
    None,
    "--from-file",
    help="Transcribe audio from a file (supports wav, mp3, m4a, ogg, flac, aac, webm). Requires ffmpeg for non-WAV formats with Wyoming provider.",
    rich_help_panel="Audio Recovery",
)
LAST_RECORDING: int = typer.Option(
    0,
    "--last-recording",
    help="Transcribe a saved recording. Use 1 for most recent, 2 for second-to-last, etc. Use 0 to disable (default).",
    rich_help_panel="Audio Recovery",
)
SAVE_RECORDING: bool = typer.Option(
    True,  # noqa: FBT003
    "--save-recording/--no-save-recording",
    help="Save the audio recording to disk for recovery.",
    rich_help_panel="Audio Recovery",
)
