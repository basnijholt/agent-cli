"""An chat agent that you can talk to.

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
    OllamaLLMConfig,
    OpenAIASRConfig,
    OpenAILLMConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingASRConfig,
    WyomingTTSConfig,
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
    start_time = time.monotonic()
    transcriber = asr.get_transcriber(asr_config)
    instruction = await transcriber(
        asr_config=asr_config,
        logger=LOGGER,
        p=p,
        stop_event=stop_event,
        quiet=general_cfg.quiet,
        live=live,
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
    start_time = time.monotonic()

    model_name = llm_config.config.model
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
            llm_config=llm_config,
            logger=LOGGER,
            tools=tools,
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
            text=response_text,
            tts_config=tts_config,
            save_file=file_config.save_file,
            quiet=general_cfg.quiet,
            logger=LOGGER,
            play_audio=not file_config.save_file,
            stop_event=stop_event,
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
            conversation_history = []
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


@app.command("chat")
def chat(
    *,
    # --- Provider Selection ---
    asr_provider: str = opts.ASR_PROVIDER,
    llm_provider: str = opts.LLM_PROVIDER,
    tts_provider: str = opts.TTS_PROVIDER,
    # --- ASR (Audio) Configuration ---
    input_device_index: int | None = opts.DEVICE_INDEX,
    input_device_name: str | None = opts.DEVICE_NAME,
    wyoming_asr_ip: str = opts.WYOMING_ASR_SERVER_IP,
    wyoming_asr_port: int = opts.WYOMING_ASR_SERVER_PORT,
    openai_asr_model: str = opts.OPENAI_ASR_MODEL,
    # --- LLM Configuration ---
    ollama_model: str = opts.OLLAMA_MODEL,
    ollama_host: str = opts.OLLAMA_HOST,
    openai_llm_model: str = opts.OPENAI_LLM_MODEL,
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    # --- TTS Configuration ---
    enable_tts: bool = opts.ENABLE_TTS,
    output_device_index: int | None = opts.OUTPUT_DEVICE_INDEX,
    output_device_name: str | None = opts.OUTPUT_DEVICE_NAME,
    tts_speed: float = opts.TTS_SPEED,
    wyoming_tts_ip: str = opts.WYOMING_TTS_SERVER_IP,
    wyoming_tts_port: int = opts.WYOMING_TTS_SERVER_PORT,
    wyoming_voice: str | None = opts.WYOMING_VOICE_NAME,
    wyoming_tts_language: str | None = opts.WYOMING_TTS_LANGUAGE,
    wyoming_speaker: str | None = opts.WYOMING_SPEAKER,
    openai_tts_model: str = opts.OPENAI_TTS_MODEL,
    openai_tts_voice: str = opts.OPENAI_TTS_VOICE,
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
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """An chat agent that you can talk to."""
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=False,  # Not used in chat mode
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

    with process_manager.pid_file_context(process_name), suppress(KeyboardInterrupt):
        # --- ASR Config ---
        wyoming_asr_config = WyomingASRConfig(
            server_ip=wyoming_asr_ip,
            server_port=wyoming_asr_port,
        )
        openai_asr_config = OpenAIASRConfig(model=openai_asr_model, api_key=openai_api_key)
        asr_config = ASRConfig(
            provider=asr_provider,  # type: ignore[arg-type]
            input_device_index=input_device_index,
            input_device_name=input_device_name,
            local=wyoming_asr_config,
            openai=openai_asr_config,
        )

        # --- LLM Config ---
        ollama_llm_config = OllamaLLMConfig(model=ollama_model, host=ollama_host)
        openai_llm_config = OpenAILLMConfig(model=openai_llm_model, api_key=openai_api_key)
        llm_config = LLMConfig(
            provider=llm_provider,  # type: ignore[arg-type]
            local=ollama_llm_config,
            openai=openai_llm_config,
        )

        # --- TTS Config ---
        wyoming_tts_config = WyomingTTSConfig(
            server_ip=wyoming_tts_ip,
            server_port=wyoming_tts_port,
            voice_name=wyoming_voice,
            language=wyoming_tts_language,
            speaker=wyoming_speaker,
        )
        openai_tts_config = OpenAITTSConfig(
            model=openai_tts_model,
            voice=openai_tts_voice,
            api_key=openai_api_key,
        )
        tts_config = TTSConfig(
            enabled=enable_tts,
            provider=tts_provider,  # type: ignore[arg-type]
            output_device_index=output_device_index,
            output_device_name=output_device_name,
            speed=tts_speed,
            local=wyoming_tts_config,
            openai=openai_tts_config,
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
