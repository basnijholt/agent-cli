"""Voice-based conversational chat agent with memory and tools.

Runs an interactive voice loop: listens for speech, transcribes it,
sends to the LLM (with conversation context), and optionally speaks the response.

**Available tools** (automatically used by the LLM when relevant):
- `add_memory`/`search_memory`/`update_memory` - persistent long-term memory
- `duckduckgo_search` - web search for current information
- `read_file`/`execute_code` - file access and shell commands

**Process management**: Use `--toggle` to start/stop via hotkey, `--stop` to terminate,
or `--status` to check if running. Useful for binding to a keyboard shortcut.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import typer

from agent_cli import config, opts
from agent_cli._tools import tools
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import setup_devices
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import (
    InteractiveStopEvent,
    console,
    format_timedelta_to_ago,
    live_timer,
    maybe_live,
    print_command_line_args,
    print_input_panel,
    print_output_panel,
    print_with_style,
    setup_logging,
    signal_handling_context,
    stop_or_status_or_toggle,
)
from agent_cli.services import asr
from agent_cli.services.llm import get_llm_response
from agent_cli.services.tts import handle_tts_playback

if TYPE_CHECKING:
    from rich.live import Live


LOGGER = logging.getLogger(__name__)

# --- Conversation History ---


class ConversationEntry(TypedDict):
    """A single entry in the conversation."""

    role: str
    content: str
    timestamp: str


# --- LLM Prompts ---

SYSTEM_PROMPT = """\
You are a helpful and friendly conversational AI with long-term memory. Your role is to assist the user with their questions and tasks.

You have access to the following tools:
- read_file: Read the content of a file.
- execute_code: Execute a shell command.
- add_memory: Add important information to long-term memory for future recall.
- search_memory: Search your long-term memory for relevant information.
- update_memory: Modify existing memories by ID when information changes.
- list_all_memories: Show all stored memories with their IDs and details.
- list_memory_categories: See what types of information you've remembered.
- duckduckgo_search: Search the web for current information.

Memory Guidelines:
- When the user shares personal information, preferences, or important facts, offer to add them to memory.
- Before answering questions, consider searching your memory for relevant context.
- Use categories like: personal, preferences, facts, tasks, projects, etc.
- Always ask for permission before adding sensitive or personal information to memory.

- The user is interacting with you through voice, so keep your responses concise and natural.
- A summary of the previous conversation is provided for context. This context may or may not be relevant to the current query.
- Do not repeat information from the previous conversation unless it is necessary to answer the current question.
- Do not ask "How can I help you?" at the end of your response.
"""

AGENT_INSTRUCTIONS = """\
A summary of the previous conversation is provided in the <previous-conversation> tag.
The user's current message is in the <user-message> tag.

- If the user's message is a continuation of the previous conversation, use the context to inform your response.
- If the user's message is a new topic, ignore the previous conversation.

Your response should be helpful and directly address the user's message.
"""

USER_MESSAGE_WITH_CONTEXT_TEMPLATE = """
<previous-conversation>
{formatted_history}
</previous-conversation>
<user-message>
{instruction}
</user-message>
"""

# --- Helper Functions ---


def _load_conversation_history(history_file: Path, last_n_messages: int) -> list[ConversationEntry]:
    if last_n_messages == 0:
        return []
    if history_file.exists():
        with history_file.open("r") as f:
            history = json.load(f)
            if last_n_messages > 0:
                return history[-last_n_messages:]
            return history
    return []


def _save_conversation_history(history_file: Path, history: list[ConversationEntry]) -> None:
    with history_file.open("w") as f:
        json.dump(history, f, indent=2)


def _format_conversation_for_llm(history: list[ConversationEntry]) -> str:
    """Format the conversation history for the LLM."""
    if not history:
        return "No previous conversation."

    now = datetime.now(UTC)
    formatted_lines = []
    for entry in history:
        timestamp = datetime.fromisoformat(entry["timestamp"])
        ago = format_timedelta_to_ago(now - timestamp)
        formatted_lines.append(f"{entry['role']} ({ago}): {entry['content']}")
    return "\n".join(formatted_lines)


async def _handle_conversation_turn(
    *,
    stop_event: InteractiveStopEvent,
    conversation_history: list[ConversationEntry],
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    history_cfg: config.History,
    audio_in_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    audio_out_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS,
    live: Live,
) -> None:
    """Handles a single turn of the conversation."""
    # 1. Transcribe user's command
    start_time = time.monotonic()
    transcriber = asr.create_transcriber(
        provider_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
    )
    instruction = await transcriber(
        stop_event=stop_event,
        quiet=general_cfg.quiet,
        live=live,
        logger=LOGGER,
    )
    elapsed = time.monotonic() - start_time

    # Clear the stop event after ASR completes - it was only meant to stop recording
    stop_event.clear()

    if not instruction or not instruction.strip():
        if not general_cfg.quiet:
            print_with_style(
                "No instruction, listening again.",
                style="yellow",
            )
        return

    if not general_cfg.quiet:
        print_input_panel(instruction, title="👤 You", subtitle=f"took {elapsed:.2f}s")

    # 2. Add user message to history
    conversation_history.append(
        {
            "role": "user",
            "content": instruction,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # 3. Format conversation for LLM
    formatted_history = _format_conversation_for_llm(conversation_history)
    user_message_with_context = USER_MESSAGE_WITH_CONTEXT_TEMPLATE.format(
        formatted_history=formatted_history,
        instruction=instruction,
    )

    # 4. Get LLM response with timing

    start_time = time.monotonic()

    if provider_cfg.llm_provider == "ollama":
        model_name = ollama_cfg.llm_ollama_model
    elif provider_cfg.llm_provider == "openai":
        model_name = openai_llm_cfg.llm_openai_model
    elif provider_cfg.llm_provider == "gemini":
        model_name = gemini_llm_cfg.llm_gemini_model
    async with live_timer(
        live,
        f"🤖 Processing with {model_name}",
        style="bold yellow",
        quiet=general_cfg.quiet,
        stop_event=stop_event,
    ):
        response_text = await get_llm_response(
            system_prompt=SYSTEM_PROMPT,
            agent_instructions=AGENT_INSTRUCTIONS,
            user_input=user_message_with_context,
            provider_cfg=provider_cfg,
            ollama_cfg=ollama_cfg,
            openai_cfg=openai_llm_cfg,
            gemini_cfg=gemini_llm_cfg,
            logger=LOGGER,
            tools=tools(),
            quiet=True,  # Suppress internal output since we're showing our own timer
            live=live,
        )

    elapsed = time.monotonic() - start_time

    if not response_text:
        if not general_cfg.quiet:
            print_with_style("No response from LLM.", style="yellow")
        return

    if not general_cfg.quiet:
        print_output_panel(
            response_text,
            title="🤖 AI",
            subtitle=f"[dim]took {elapsed:.2f}s[/dim]",
        )

    # 5. Add AI response to history
    conversation_history.append(
        {
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # 6. Save history
    if history_cfg.history_dir:
        history_path = Path(history_cfg.history_dir).expanduser()
        history_path.mkdir(parents=True, exist_ok=True)
        # Share the history directory with the memory tools
        os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
        history_file = history_path / "conversation.json"
        _save_conversation_history(history_file, conversation_history)

    # 7. Handle TTS playback
    if audio_out_cfg.enable_tts:
        await handle_tts_playback(
            text=response_text,
            provider_cfg=provider_cfg,
            audio_output_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
            save_file=general_cfg.save_file,
            quiet=general_cfg.quiet,
            logger=LOGGER,
            play_audio=not general_cfg.save_file,
            stop_event=stop_event,
            live=live,
        )

    # Reset stop_event for next iteration
    stop_event.clear()


# --- Main Application Logic ---


async def _async_main(
    *,
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    history_cfg: config.History,
    audio_in_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    audio_out_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS,
) -> None:
    """Main async function, consumes parsed arguments."""
    try:
        device_info = setup_devices(general_cfg, audio_in_cfg, audio_out_cfg)
        if device_info is None:
            return
        input_device_index, _, tts_output_device_index = device_info
        audio_in_cfg.input_device_index = input_device_index
        if audio_out_cfg.enable_tts:
            audio_out_cfg.output_device_index = tts_output_device_index

        # Load conversation history
        conversation_history = []
        if history_cfg.history_dir:
            history_path = Path(history_cfg.history_dir).expanduser()
            history_path.mkdir(parents=True, exist_ok=True)
            # Share the history directory with the memory tools
            os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
            history_file = history_path / "conversation.json"
            conversation_history = _load_conversation_history(
                history_file,
                history_cfg.last_n_messages,
            )

        with (
            maybe_live(not general_cfg.quiet) as live,
            signal_handling_context(LOGGER, general_cfg.quiet) as stop_event,
        ):
            while not stop_event.is_set():
                await _handle_conversation_turn(
                    stop_event=stop_event,
                    conversation_history=conversation_history,
                    provider_cfg=provider_cfg,
                    general_cfg=general_cfg,
                    history_cfg=history_cfg,
                    audio_in_cfg=audio_in_cfg,
                    wyoming_asr_cfg=wyoming_asr_cfg,
                    openai_asr_cfg=openai_asr_cfg,
                    gemini_asr_cfg=gemini_asr_cfg,
                    ollama_cfg=ollama_cfg,
                    openai_llm_cfg=openai_llm_cfg,
                    gemini_llm_cfg=gemini_llm_cfg,
                    audio_out_cfg=audio_out_cfg,
                    wyoming_tts_cfg=wyoming_tts_cfg,
                    openai_tts_cfg=openai_tts_cfg,
                    kokoro_tts_cfg=kokoro_tts_cfg,
                    gemini_tts_cfg=gemini_tts_cfg,
                    live=live,
                )
    except Exception:
        if not general_cfg.quiet:
            console.print_exception()
        raise


@app.command("chat", rich_help_panel="Voice Commands")
@requires_extras("audio", "llm")
def chat(
    *,
    # --- Provider Selection ---
    asr_provider: str = opts.ASR_PROVIDER,
    llm_provider: str = opts.LLM_PROVIDER,
    tts_provider: str = opts.TTS_PROVIDER,
    # --- ASR (Audio) Configuration ---
    input_device_index: int | None = opts.INPUT_DEVICE_INDEX,
    input_device_name: str | None = opts.INPUT_DEVICE_NAME,
    asr_wyoming_ip: str = opts.ASR_WYOMING_IP,
    asr_wyoming_port: int = opts.ASR_WYOMING_PORT,
    asr_openai_model: str = opts.ASR_OPENAI_MODEL,
    asr_openai_base_url: str | None = opts.ASR_OPENAI_BASE_URL,
    asr_openai_prompt: str | None = opts.ASR_OPENAI_PROMPT,
    asr_gemini_model: str = opts.ASR_GEMINI_MODEL,
    # --- LLM Configuration ---
    llm_ollama_model: str = opts.LLM_OLLAMA_MODEL,
    llm_ollama_host: str = opts.LLM_OLLAMA_HOST,
    llm_openai_model: str = opts.LLM_OPENAI_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    llm_gemini_model: str = opts.LLM_GEMINI_MODEL,
    gemini_api_key: str | None = opts.GEMINI_API_KEY,
    # --- TTS Configuration ---
    enable_tts: bool = opts.ENABLE_TTS,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    tts_speed: float = opts.TTS_SPEED,
    tts_wyoming_ip: str = opts.TTS_WYOMING_IP,
    tts_wyoming_port: int = opts.TTS_WYOMING_PORT,
    tts_wyoming_voice: str | None = opts.TTS_WYOMING_VOICE,
    tts_wyoming_language: str | None = opts.TTS_WYOMING_LANGUAGE,
    tts_wyoming_speaker: str | None = opts.TTS_WYOMING_SPEAKER,
    tts_openai_model: str = opts.TTS_OPENAI_MODEL,
    tts_openai_voice: str = opts.TTS_OPENAI_VOICE,
    tts_openai_base_url: str | None = opts.TTS_OPENAI_BASE_URL,
    tts_kokoro_model: str = opts.TTS_KOKORO_MODEL,
    tts_kokoro_voice: str = opts.TTS_KOKORO_VOICE,
    tts_kokoro_host: str = opts.TTS_KOKORO_HOST,
    tts_gemini_model: str = opts.TTS_GEMINI_MODEL,
    tts_gemini_voice: str = opts.TTS_GEMINI_VOICE,
    # --- Process Management ---
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # --- History Options ---
    history_dir: Path = typer.Option(  # noqa: B008
        "~/.config/agent-cli/history",
        "--history-dir",
        help="Directory for conversation history and long-term memory. "
        "Both `conversation.json` and `long_term_memory.json` are stored here.",
        rich_help_panel="History Options",
    ),
    last_n_messages: int = typer.Option(
        50,
        "--last-n-messages",
        help="Number of past messages to include as context for the LLM. "
        "Set to 0 to start fresh each session (memory tools still persist).",
        rich_help_panel="History Options",
    ),
    # --- General Options ---
    save_file: Path | None = opts.SAVE_FILE,
    log_level: opts.LogLevel = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Voice-based conversational chat agent with memory and tools.

    Runs an interactive loop: listen → transcribe → LLM → speak response.
    Conversation history is persisted and included as context for continuity.

    **Built-in tools** (LLM uses automatically when relevant):

    - `add_memory`/`search_memory`/`update_memory` - persistent long-term memory
    - `duckduckgo_search` - web search for current information
    - `read_file`/`execute_code` - file access and shell commands

    **Process management**: Use `--toggle` to start/stop via hotkey (bind to
    a keyboard shortcut), `--stop` to terminate, or `--status` to check state.

    **Examples**:

    Use OpenAI-compatible providers for speech and LLM, with TTS enabled:

        agent-cli chat --asr-provider openai --llm-provider openai --tts

    Start in background mode (toggle on/off with hotkey):

        agent-cli chat --toggle

    Use local Ollama LLM with Wyoming ASR:

        agent-cli chat --llm-provider ollama
    """
    if print_args:
        print_command_line_args(locals())

    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,  # Not used in chat mode
        save_file=save_file,
    )
    process_name = "chat"
    if stop_or_status_or_toggle(
        process_name,
        "chat agent",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        cfgs = config.create_provider_configs_from_locals(locals())
        history_cfg = config.History(
            history_dir=history_dir,
            last_n_messages=last_n_messages,
        )

        asyncio.run(
            _async_main(
                provider_cfg=cfgs.provider,
                general_cfg=general_cfg,
                history_cfg=history_cfg,
                audio_in_cfg=cfgs.audio_in,
                wyoming_asr_cfg=cfgs.wyoming_asr,
                openai_asr_cfg=cfgs.openai_asr,
                gemini_asr_cfg=cfgs.gemini_asr,
                ollama_cfg=cfgs.ollama,
                openai_llm_cfg=cfgs.openai_llm,
                gemini_llm_cfg=cfgs.gemini_llm,
                audio_out_cfg=cfgs.audio_out,
                wyoming_tts_cfg=cfgs.wyoming_tts,
                openai_tts_cfg=cfgs.openai_tts,
                kokoro_tts_cfg=cfgs.kokoro_tts,
                gemini_tts_cfg=cfgs.gemini_tts,
            ),
        )
