"""An interactive chat agent with voice and text input.

This agent supports:
- Live transcription mode: Text appears as you speak, editable before sending
- Direct voice mode: Speak until Ctrl+C, then send
- Pause/resume: Mute mic to talk to someone else (Escape key)
- Slash commands: /tts, /mode, /tools, /clear, /help
- Text input: Type messages directly instead of speaking
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
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.panel import Panel
from rich.text import Text

from agent_cli import config, opts
from agent_cli._tools import tools
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import setup_devices
from agent_cli.core.chat_state import (
    ChatSessionState,
    handle_slash_command,
    parse_slash_command,
)
from agent_cli.core.utils import (
    InteractiveStopEvent,
    console,
    format_timedelta_to_ago,
    live_timer,
    print_command_line_args,
    print_input_panel,
    print_output_panel,
    print_with_style,
    setup_logging,
    signal_handling_context,
    stop_or_status_or_toggle,
)
from agent_cli.core.voice_input import (
    VoiceInputState,
    VoiceInputStatus,
    create_transcriber_from_config,
    run_voice_input_loop,
)
from agent_cli.services import asr
from agent_cli.services.llm import get_llm_response
from agent_cli.services.tts import handle_tts_playback

if TYPE_CHECKING:
    from rich.live import Live

    from agent_cli.core.vad import VoiceActivityDetector


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

# --- Status Display ---

STATUS_ICONS = {
    VoiceInputStatus.LISTENING: "🎤 Listening",
    VoiceInputStatus.RECORDING: "🔴 Recording...",
    VoiceInputStatus.PROCESSING: "⏳ Processing...",
    VoiceInputStatus.PAUSED: "⏸️  Paused [Esc]",
    VoiceInputStatus.READY: "✓ Ready [Enter]",
}


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


def _get_active_tools(state: ChatSessionState) -> list:
    """Get list of tools with disabled ones filtered out."""
    all_tools = tools()
    if not state.disabled_tools:
        return all_tools
    return [t for t in all_tools if t.function.__name__ not in state.disabled_tools]


def _create_input_panel(text: str, status: VoiceInputStatus) -> Panel:
    """Create the input panel with current text and status."""
    status_text = STATUS_ICONS.get(status, "")
    content = Text()
    content.append(text if text else "")
    content.append("_", style="blink")  # Cursor
    content.append("\n")
    content.append(" " * 30)  # Spacing
    content.append(status_text, style="dim")

    return Panel(
        content,
        title="Your message",
        border_style="blue",
        padding=(0, 1),
    )


# --- Live Input Mode ---


async def _get_live_input(
    *,
    vad: VoiceActivityDetector,
    provider_cfg: config.ProviderSelection,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    wyoming_asr_cfg: config.WyomingASR,
    input_device_index: int | None,
    quiet: bool,
) -> str:
    """Get input via live transcription with editing.

    Returns the final text to send, or empty string if cancelled.
    """
    voice_state = VoiceInputState()
    stop_event = asyncio.Event()

    # Create transcriber
    transcriber = create_transcriber_from_config(
        provider_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
        wyoming_asr_cfg,
        LOGGER,
        quiet=True,
    )

    # Create prompt session with key bindings
    bindings = KeyBindings()

    @bindings.add("escape")
    def toggle_pause(event: object) -> None:  # noqa: ARG001
        voice_state.is_paused = not voice_state.is_paused
        if not quiet:
            status_msg = "⏸️  Paused" if voice_state.is_paused else "🎤 Resumed"
            console.print(f"[dim]{status_msg}[/dim]", end="\r")

    session: PromptSession[str] = PromptSession(key_bindings=bindings)
    current_status = VoiceInputStatus.LISTENING

    def on_status_change(new_status: VoiceInputStatus) -> None:
        nonlocal current_status
        current_status = new_status
        if not quiet:
            # Update the status display
            status_text = STATUS_ICONS.get(new_status, "")
            console.print(f"[dim]{status_text}[/dim]" + " " * 20, end="\r")

    def on_text_update(text: str) -> None:
        # Update the prompt buffer with the new text
        session.default_buffer.text = text
        session.default_buffer.cursor_position = len(text)

    # Start voice input loop in background
    voice_task = asyncio.create_task(
        run_voice_input_loop(
            vad=vad,
            transcriber=transcriber,
            state=voice_state,
            on_status_change=on_status_change,
            on_text_update=on_text_update,
            stop_event=stop_event,
            input_device_index=input_device_index,
            logger=LOGGER,
        ),
    )

    try:
        if not quiet:
            console.print("[dim]🎤 Listening (Esc=pause, Enter=send, type to switch to text)[/dim]")

        # Run prompt (user can edit, Enter to submit)
        with patch_stdout():
            result = await session.prompt_async("│ ")

        return result.strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        stop_event.set()
        voice_task.cancel()
        with suppress(asyncio.CancelledError):
            await voice_task


# --- Direct Input Mode ---


async def _get_direct_input(
    *,
    stop_event: InteractiveStopEvent,
    provider_cfg: config.ProviderSelection,
    audio_in_cfg: config.AudioInput,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
    quiet: bool,
    live: Live,
) -> str:
    """Get input via direct voice mode (original behavior).

    Speak until Ctrl+C, then transcribe and return.
    """
    transcriber = asr.create_transcriber(
        provider_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
    )
    instruction = await transcriber(
        stop_event=stop_event,
        quiet=quiet,
        live=live,
        logger=LOGGER,
    )
    return instruction.strip() if instruction else ""


# --- Conversation Turn Handler ---


async def _handle_conversation_turn(
    *,
    instruction: str,
    chat_state: ChatSessionState,
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
    history_cfg: config.History,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
    audio_out_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS,
    live: Live,
    stop_event: InteractiveStopEvent,
) -> None:
    """Handles a single turn of the conversation (after input is received)."""
    if not general_cfg.quiet:
        print_input_panel(instruction, title="👤 You")

    # Add user message to history
    chat_state.conversation_history.append(
        {
            "role": "user",
            "content": instruction,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Format conversation for LLM
    formatted_history = _format_conversation_for_llm(chat_state.conversation_history)
    user_message_with_context = USER_MESSAGE_WITH_CONTEXT_TEMPLATE.format(
        formatted_history=formatted_history,
        instruction=instruction,
    )

    # Get LLM response with timing
    start_time = time.monotonic()

    if provider_cfg.llm_provider == "ollama":
        model_name = ollama_cfg.llm_ollama_model
    elif provider_cfg.llm_provider == "openai":
        model_name = openai_llm_cfg.llm_openai_model
    elif provider_cfg.llm_provider == "gemini":
        model_name = gemini_llm_cfg.llm_gemini_model
    else:
        model_name = "unknown"

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
            tools=_get_active_tools(chat_state),
            quiet=True,
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

    # Add AI response to history
    chat_state.conversation_history.append(
        {
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Save history
    if history_cfg.history_dir:
        history_path = Path(history_cfg.history_dir).expanduser()
        history_path.mkdir(parents=True, exist_ok=True)
        os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
        history_file = history_path / "conversation.json"
        _save_conversation_history(history_file, chat_state.conversation_history)

    # Handle TTS playback if enabled in session state
    if chat_state.tts_enabled and audio_out_cfg.enable_tts:
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


# --- Main Application Logic ---


async def _async_main(  # noqa: PLR0912, PLR0915
    *,
    vad: VoiceActivityDetector,
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
    """Main async function for interactive chat."""
    try:
        device_info = setup_devices(general_cfg, audio_in_cfg, audio_out_cfg)
        if device_info is None:
            return
        input_device_index, _, tts_output_device_index = device_info
        audio_in_cfg.input_device_index = input_device_index
        if audio_out_cfg.enable_tts:
            audio_out_cfg.output_device_index = tts_output_device_index

        # Initialize chat session state
        chat_state = ChatSessionState(tts_enabled=audio_out_cfg.enable_tts)

        # Load conversation history
        if history_cfg.history_dir:
            history_path = Path(history_cfg.history_dir).expanduser()
            history_path.mkdir(parents=True, exist_ok=True)
            os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
            history_file = history_path / "conversation.json"
            chat_state.conversation_history = _load_conversation_history(
                history_file,
                history_cfg.last_n_messages,
            )

        # Show startup message
        if not general_cfg.quiet:
            tts_status = "on" if chat_state.tts_enabled else "off"
            mode_status = chat_state.input_mode
            print_with_style(
                f"🎙️ Chat started (mode: {mode_status}, TTS: {tts_status})",
                style="green",
            )
            print_with_style("   Type /help for commands, Ctrl+C to exit", style="dim")
            console.print()

        with signal_handling_context(LOGGER, general_cfg.quiet) as stop_event:
            # Use a simple Live context for the direct mode
            from rich.live import Live  # noqa: PLC0415

            live = Live(console=console, transient=True)

            while not stop_event.is_set():
                try:
                    # Get user input based on current mode
                    if chat_state.input_mode == "live":
                        instruction = await _get_live_input(
                            vad=vad,
                            provider_cfg=provider_cfg,
                            openai_asr_cfg=openai_asr_cfg,
                            gemini_asr_cfg=gemini_asr_cfg,
                            wyoming_asr_cfg=wyoming_asr_cfg,
                            input_device_index=audio_in_cfg.input_device_index,
                            quiet=general_cfg.quiet,
                        )
                    else:
                        # Direct mode
                        if not general_cfg.quiet:
                            print_with_style(
                                "🎤 Listening... (Ctrl+C to finish)",
                                style="blue",
                            )
                        with live:
                            instruction = await _get_direct_input(
                                stop_event=stop_event,
                                provider_cfg=provider_cfg,
                                audio_in_cfg=audio_in_cfg,
                                wyoming_asr_cfg=wyoming_asr_cfg,
                                openai_asr_cfg=openai_asr_cfg,
                                gemini_asr_cfg=gemini_asr_cfg,
                                quiet=general_cfg.quiet,
                                live=live,
                            )
                        # Clear stop event after direct input
                        stop_event.clear()

                    if not instruction:
                        if not general_cfg.quiet:
                            print_with_style("No input received.", style="yellow")
                        continue

                    # Check for slash command
                    parsed = parse_slash_command(instruction)
                    if parsed:
                        command, args = parsed
                        result = handle_slash_command(command, args, chat_state)
                        if not general_cfg.quiet:
                            console.print(f"[dim]{result}[/dim]")
                        continue

                    # Handle conversation turn
                    with live:
                        await _handle_conversation_turn(
                            instruction=instruction,
                            chat_state=chat_state,
                            provider_cfg=provider_cfg,
                            general_cfg=general_cfg,
                            history_cfg=history_cfg,
                            ollama_cfg=ollama_cfg,
                            openai_llm_cfg=openai_llm_cfg,
                            gemini_llm_cfg=gemini_llm_cfg,
                            audio_out_cfg=audio_out_cfg,
                            wyoming_tts_cfg=wyoming_tts_cfg,
                            openai_tts_cfg=openai_tts_cfg,
                            kokoro_tts_cfg=kokoro_tts_cfg,
                            gemini_tts_cfg=gemini_tts_cfg,
                            live=live,
                            stop_event=stop_event,
                        )

                except KeyboardInterrupt:
                    # In live mode, Ctrl+C exits; in direct mode, it ends recording
                    if chat_state.input_mode == "live":
                        break
                    # For direct mode, the stop_event handles it
                    continue

    except Exception:
        if not general_cfg.quiet:
            console.print_exception()
        raise


@app.command("chat")
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
    # --- VAD Configuration ---
    vad_threshold: float = typer.Option(
        0.3,
        "--vad-threshold",
        help="VAD speech detection threshold (0.0-1.0). Higher = more aggressive filtering.",
        rich_help_panel="VAD Options",
    ),
    silence_threshold: float = typer.Option(
        1.0,
        "--silence-threshold",
        help="Seconds of silence to end a speech segment.",
        rich_help_panel="VAD Options",
    ),
    # --- Process Management ---
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # --- History Options ---
    history_dir: Path = typer.Option(  # noqa: B008
        "~/.config/agent-cli/history",
        "--history-dir",
        help="Directory to store conversation history.",
        rich_help_panel="History Options",
    ),
    last_n_messages: int = typer.Option(
        50,
        "--last-n-messages",
        help="Number of messages to include in the conversation history."
        " Set to 0 to disable history.",
        rich_help_panel="History Options",
    ),
    # --- General Options ---
    save_file: Path | None = opts.SAVE_FILE,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """An interactive chat agent with voice and text input.

    Supports two input modes:
    - Live mode (default): Speak and see transcription appear, edit before sending
    - Direct mode: Speak until Ctrl+C, then send immediately

    Use /help during chat to see available commands.
    """
    if print_args:
        print_command_line_args(locals())
    setup_logging(log_level, log_file, quiet=quiet)

    # Check VAD is available
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        print_with_style(
            "❌ VAD required for chat. Install with: pip install agent-cli[vad]",
            style="red",
        )
        print_with_style(
            "   Or: uv sync --extra vad",
            style="dim",
        )
        raise typer.Exit(1) from None

    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,
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

    # Validate VAD threshold
    if vad_threshold < 0.0 or vad_threshold > 1.0:
        print_with_style("❌ VAD threshold must be 0.0-1.0", style="red")
        raise typer.Exit(1)

    # Create VAD instance
    vad = VoiceActivityDetector(
        threshold=vad_threshold,
        silence_threshold_ms=int(silence_threshold * 1000),
    )

    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        provider_cfg = config.ProviderSelection(
            asr_provider=asr_provider,
            llm_provider=llm_provider,
            tts_provider=tts_provider,
        )
        audio_in_cfg = config.AudioInput(
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip=asr_wyoming_ip,
            asr_wyoming_port=asr_wyoming_port,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model=asr_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=asr_openai_base_url,
            asr_openai_prompt=asr_openai_prompt,
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model=asr_gemini_model,
            gemini_api_key=gemini_api_key,
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model=llm_ollama_model,
            llm_ollama_host=llm_ollama_host,
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=llm_openai_model,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model=llm_gemini_model,
            gemini_api_key=gemini_api_key,
        )
        audio_out_cfg = config.AudioOutput(
            enable_tts=enable_tts,
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            tts_speed=tts_speed,
        )
        wyoming_tts_cfg = config.WyomingTTS(
            tts_wyoming_ip=tts_wyoming_ip,
            tts_wyoming_port=tts_wyoming_port,
            tts_wyoming_voice=tts_wyoming_voice,
            tts_wyoming_language=tts_wyoming_language,
            tts_wyoming_speaker=tts_wyoming_speaker,
        )
        openai_tts_cfg = config.OpenAITTS(
            tts_openai_model=tts_openai_model,
            tts_openai_voice=tts_openai_voice,
            openai_api_key=openai_api_key,
            tts_openai_base_url=tts_openai_base_url,
        )
        kokoro_tts_cfg = config.KokoroTTS(
            tts_kokoro_model=tts_kokoro_model,
            tts_kokoro_voice=tts_kokoro_voice,
            tts_kokoro_host=tts_kokoro_host,
        )
        gemini_tts_cfg = config.GeminiTTS(
            tts_gemini_model=tts_gemini_model,
            tts_gemini_voice=tts_gemini_voice,
            gemini_api_key=gemini_api_key,
        )
        history_cfg = config.History(
            history_dir=history_dir,
            last_n_messages=last_n_messages,
        )

        asyncio.run(
            _async_main(
                vad=vad,
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
            ),
        )

    if not quiet:
        console.print()
        print_with_style("👋 Chat ended.", style="yellow")
