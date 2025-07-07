r"""An interactive agent that you can talk to.

This agent will:
- Listen for your voice command.
- Transcribe the command.
- Send the transcription to an LLM.
- Speak the LLM's response.
- Remember the conversation history.
- Attach timestamps to the saved conversation.
- Format timestamps as "ago" when sending to the LLM.
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

import agent_cli.agents._cli_options as opts
from agent_cli import asr, process_manager
from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
)
from agent_cli.agents._tts_common import handle_tts_playback
from agent_cli.audio import pyaudio_context, setup_devices
from agent_cli.cli import app, setup_logging
from agent_cli.llm import get_llm_response
from agent_cli.utils import (
    InteractiveStopEvent,
    console,
    format_timedelta_to_ago,
    live_timer,
    maybe_live,
    print_input_panel,
    print_output_panel,
    print_with_style,
    signal_handling_context,
    stop_or_status_or_toggle,
)

if TYPE_CHECKING:
    import pyaudio
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
    p: pyaudio.PyAudio,
    stop_event: InteractiveStopEvent,
    conversation_history: list[ConversationEntry],
    general_cfg: GeneralConfig,
    asr_config: ASRConfig,
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    file_config: FileConfig,
    live: Live,
) -> None:
    """Handles a single turn of the conversation."""
    # Import here to avoid slow pydantic_ai import in CLI
    from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool  # noqa: PLC0415

    from agent_cli._tools import (  # noqa: PLC0415
        AddMemoryTool,
        ExecuteCodeTool,
        ListAllMemoriesTool,
        ListMemoryCategoresTool,
        ReadFileTool,
        SearchMemoryTool,
        UpdateMemoryTool,
    )

    # 1. Transcribe user's command
    time_start = time.monotonic()
    instruction = await asr.transcribe_live_audio(
        asr_server_ip=asr_config.server_ip,
        asr_server_port=asr_config.server_port,
        input_device_index=asr_config.input_device_index,
        logger=LOGGER,
        p=p,
        stop_event=stop_event,
        quiet=general_cfg.quiet,
        live=live,
    )
    elapsed = time.monotonic() - time_start

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
    tools = [
        ReadFileTool,
        ExecuteCodeTool,
        AddMemoryTool,
        SearchMemoryTool,
        UpdateMemoryTool,
        ListAllMemoriesTool,
        ListMemoryCategoresTool,
        duckduckgo_search_tool(),
    ]
    time_start = time.monotonic()

    async with live_timer(
        live,
        f"🤖 Processing with {llm_config.model}",
        style="bold yellow",
        quiet=general_cfg.quiet,
        stop_event=stop_event,
    ):
        # Create a dummy Live for get_llm_response since we're using our own timer display
        response_text = await get_llm_response(
            system_prompt=SYSTEM_PROMPT,
            agent_instructions=AGENT_INSTRUCTIONS,
            user_input=user_message_with_context,
            model=llm_config.model,
            ollama_host=llm_config.ollama_host,
            logger=LOGGER,
            tools=tools,
            quiet=True,  # Suppress internal output since we're showing our own timer
            live=live,
        )

    elapsed = time.monotonic() - time_start

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
    if file_config.history_dir:
        history_path = Path(file_config.history_dir).expanduser()
        history_path.mkdir(parents=True, exist_ok=True)
        # Share the history directory with the memory tools
        os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
        history_file = history_path / "conversation.json"
        _save_conversation_history(history_file, conversation_history)

    # 7. Handle TTS playback
    if tts_config.enabled:
        await handle_tts_playback(
            response_text,
            tts_server_ip=tts_config.server_ip,
            tts_server_port=tts_config.server_port,
            voice_name=tts_config.voice_name,
            tts_language=tts_config.language,
            speaker=tts_config.speaker,
            output_device_index=tts_config.output_device_index,
            save_file=file_config.save_file,
            quiet=general_cfg.quiet,
            logger=LOGGER,
            play_audio=not file_config.save_file,
            stop_event=stop_event,
            speed=tts_config.speed,
            live=live,
        )

    # Reset stop_event for next iteration
    stop_event.clear()


# --- Main Application Logic ---


async def _async_main(
    *,
    general_cfg: GeneralConfig,
    asr_config: ASRConfig,
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    file_config: FileConfig,
) -> None:
    """Main async function, consumes parsed arguments."""
    try:
        with pyaudio_context() as p:
            device_info = setup_devices(p, general_cfg, asr_config, tts_config)
            if device_info is None:
                return
            input_device_index, _, tts_output_device_index = device_info
            asr_config.input_device_index = input_device_index
            if tts_config.enabled:
                tts_config.output_device_index = tts_output_device_index

            # Load conversation history
            if file_config.history_dir:
                history_path = Path(file_config.history_dir).expanduser()
                history_path.mkdir(parents=True, exist_ok=True)
                # Share the history directory with the memory tools
                os.environ["AGENT_CLI_HISTORY_DIR"] = str(history_path)
                history_file = history_path / "conversation.json"
                conversation_history = _load_conversation_history(
                    history_file,
                    file_config.last_n_messages,
                )

            with (
                maybe_live(not general_cfg.quiet) as live,
                signal_handling_context(LOGGER, general_cfg.quiet) as stop_event,
            ):
                while not stop_event.is_set():
                    await _handle_conversation_turn(
                        p=p,
                        stop_event=stop_event,
                        conversation_history=conversation_history,
                        general_cfg=general_cfg,
                        asr_config=asr_config,
                        llm_config=llm_config,
                        tts_config=tts_config,
                        file_config=file_config,
                        live=live,
                    )
    except Exception:
        if not general_cfg.quiet:
            console.print_exception()
        raise


@app.command("interactive")
def interactive(
    *,
    # ASR
    input_device_index: int | None = opts.DEVICE_INDEX,
    input_device_name: str | None = opts.DEVICE_NAME,
    asr_server_ip: str = opts.ASR_SERVER_IP,
    asr_server_port: int = opts.ASR_SERVER_PORT,
    # LLM
    model: str = opts.MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    # Process control
    stop: bool = opts.STOP,
    status: bool = opts.STATUS,
    toggle: bool = opts.TOGGLE,
    # TTS parameters
    enable_tts: bool = opts.ENABLE_TTS,
    tts_server_ip: str = opts.TTS_SERVER_IP,
    tts_server_port: int = opts.TTS_SERVER_PORT,
    voice_name: str | None = opts.VOICE_NAME,
    tts_language: str | None = opts.TTS_LANGUAGE,
    speaker: str | None = opts.SPEAKER,
    tts_speed: float = opts.TTS_SPEED,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    # Output
    save_file: Path | None = opts.SAVE_FILE,
    # History
    history_dir: Path = typer.Option(  # noqa: B008
        "~/.config/agent-cli/history",
        "--history-dir",
        help="Directory to store conversation history.",
    ),
    last_n_messages: int = typer.Option(
        50,
        "--last-n-messages",
        help="Number of messages to include in the conversation history."
        " Set to 0 to disable history.",
    ),
    # General
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """An interactive agent that you can talk to."""
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,  # Not used in interactive mode
    )
    process_name = "interactive"
    if stop_or_status_or_toggle(
        process_name,
        "interactive agent",
        stop,
        status,
        toggle,
        quiet=general_cfg.quiet,
    ):
        return

    # Use context manager for PID file management
    with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
        asr_config = ASRConfig(
            server_ip=asr_server_ip,
            server_port=asr_server_port,
            input_device_index=input_device_index,
            input_device_name=input_device_name,
        )
        llm_config = LLMConfig(model=model, ollama_host=ollama_host)
        tts_config = TTSConfig(
            enabled=enable_tts,
            server_ip=tts_server_ip,
            server_port=tts_server_port,
            voice_name=voice_name,
            language=tts_language,
            speaker=speaker,
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            speed=tts_speed,
        )
        file_config = FileConfig(
            save_file=save_file,
            last_n_messages=last_n_messages,
            history_dir=history_dir,
        )

        asyncio.run(
            _async_main(
                general_cfg=general_cfg,
                asr_config=asr_config,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
            ),
        )
