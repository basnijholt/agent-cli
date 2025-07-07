"""Shared CLI options for agent commands."""

from __future__ import annotations

import os

import typer

from agent_cli import config

# --- Device Options ---
DEVICE_INDEX = typer.Option(
    None,
    "--input-device-index",
    "-i",
    help="Index of the input device to use.",
)
DEVICE_NAME = typer.Option(
    None,
    "--input-device-name",
    "-I",
    help="Name of the input device to use (e.g., 'MacBook Pro Microphone').",
)
OUTPUT_DEVICE_INDEX = typer.Option(
    None,
    "--output-device-index",
    "-o",
    help="Index of the output device to use.",
)
OUTPUT_DEVICE_NAME = typer.Option(
    None,
    "--output-device-name",
    "-O",
    help="Name of the output device to use (e.g., 'MacBook Pro Speakers').",
)
LIST_DEVICES = typer.Option(
    False,
    "--list-devices",
    "-l",
    help="List available audio devices and exit.",
)

# --- ASR Options ---
ASR_PROVIDER = typer.Option(
    "wyoming",
    "--asr-provider",
    help='ASR provider to use ("wyoming" or "openai").',
)
ASR_SERVER_IP = typer.Option(
    config.ASR_SERVER_IP,
    "--asr-server-ip",
    help="IP address of the ASR server.",
)
ASR_SERVER_PORT = typer.Option(
    config.ASR_SERVER_PORT,
    "--asr-server-port",
    help="Port of the ASR server.",
)
WHISPER_MODEL = typer.Option(
    "whisper-1",
    "--whisper-model",
    help="Name of the Whisper model to use.",
)

# --- LLM Options ---
LLM_PROVIDER = typer.Option(
    "ollama",
    "--llm-provider",
    help='LLM provider to use ("ollama" or "openai").',
)
MODEL = typer.Option(
    config.DEFAULT_MODEL,
    "--model",
    "-m",
    help="Name of the model to use.",
)
OLLAMA_HOST = typer.Option(
    config.OLLAMA_HOST,
    "--ollama-host",
    help="Ollama server host.",
)
LLM = typer.Option(
    False,
    "--llm",
    help="Enable LLM processing of the transcript.",
)

# --- TTS Options ---
TTS_SERVER_IP = typer.Option(
    config.TTS_SERVER_IP,
    "--tts-server-ip",
    help="IP address of the TTS server.",
)
TTS_SERVER_PORT = typer.Option(
    config.TTS_SERVER_PORT,
    "--tts-server-port",
    help="Port of the TTS server.",
)
VOICE_NAME = typer.Option(
    None,
    "--voice-name",
    "-v",
    help="Name of the voice to use for TTS.",
)
TTS_LANGUAGE = typer.Option(
    None,
    "--tts-language",
    help="Language to use for TTS.",
)
SPEAKER = typer.Option(
    None,
    "--speaker",
    help="Speaker to use for TTS.",
)
TTS_SPEED = typer.Option(
    1.0,
    "--tts-speed",
    help="TTS speech speed.",
)
ENABLE_TTS = typer.Option(
    False,
    "--enable-tts",
    help="Enable text-to-speech output.",
)

# --- Wake Word Options ---
WAKE_WORD_SERVER_IP = typer.Option(
    config.WAKE_WORD_SERVER_IP,
    "--wake-word-server-ip",
    help="IP address of the wake word server.",
)
WAKE_WORD_SERVER_PORT = typer.Option(
    config.WAKE_WORD_SERVER_PORT,
    "--wake-word-server-port",
    help="Port of the wake word server.",
)
WAKE_WORD_NAME = typer.Option(
    "ok_nabu",
    "--wake-word-name",
    help="Name of the wake word to listen for.",
)

# --- Process Control Options ---
STOP = typer.Option(
    False,
    "--stop",
    help="Stop the background process.",
)
STATUS = typer.Option(
    False,
    "--status",
    help="Check the status of the background process.",
)
TOGGLE = typer.Option(
    False,
    "--toggle",
    help="Toggle the background process on/off.",
)

# --- General Options ---
SAVE_FILE = typer.Option(
    None,
    "--save-file",
    help="Save audio to WAV file instead of playing it.",
)
CLIPBOARD = typer.Option(
    True,
    "--clipboard/--no-clipboard",
    "-c/-C",
    help="Copy the result to the clipboard.",
)
LOG_LEVEL = typer.Option(
    "INFO",
    "--log-level",
    help="Set the log level (e.g., DEBUG, INFO, WARNING).",
)
LOG_FILE = typer.Option(
    None,
    "--log-file",
    help="Path to a file to write logs to.",
)
QUIET = typer.Option(
    False,
    "--quiet",
    "-q",
    help="Suppress all output except for the final result.",
)
CONFIG_FILE = typer.Option(
    None,
    "--config-file",
    help="Path to a custom config file.",
)
OPENAI_API_KEY = typer.Option(
    os.getenv("OPENAI_API_KEY"),
    "--openai-api-key",
    help="OpenAI API key.",
)
