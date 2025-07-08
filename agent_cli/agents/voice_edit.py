"""Interact with clipboard text via a voice command using Wyoming and an Ollama LLM.

WORKFLOW:
1. The script starts and immediately copies the current content of the clipboard.
2. It then starts listening for a voice command via the microphone.
3. The user triggers a stop signal (e.g., via a Keyboard Maestro hotkey sending SIGINT).
4. The script stops recording and finalizes the transcription of the voice command.
5. It sends the original clipboard text and the transcribed command to a local LLM.
6. The LLM processes the text based on the instruction (either editing it or answering a question).
7. The resulting text is then copied back to the clipboard.

KEYBOARD MAESTRO INTEGRATION:
To create a hotkey toggle for this script, set up a Keyboard Maestro macro with:

1. Trigger: Hot Key (e.g., Cmd+Shift+A for "Assistant")

2. If/Then/Else Action:
   - Condition: Shell script returns success
   - Script: voice-edit --status >/dev/null 2>&1

3. Then Actions (if process is running):
   - Display Text Briefly: "🗣️ Processing command..."
   - Execute Shell Script: voice-edit --stop --quiet
   - (The script will show its own "Done" notification)

4. Else Actions (if process is not running):
   - Display Text Briefly: "📋 Listening for command..."
   - Execute Shell Script: voice-edit --input-device-index 1 --quiet &
   - Select "Display results in a notification"

This approach uses standard Unix background processes (&) instead of Python daemons!
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path  # noqa: TC003

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
from agent_cli.agents._voice_agent_common import (
    get_instruction_from_audio,
    process_instruction_and_respond,
)
from agent_cli.audio import pyaudio_context, setup_devices
from agent_cli.cli import app, setup_logging
from agent_cli.utils import (
    get_clipboard_text,
    maybe_live,
    print_input_panel,
    print_with_style,
    signal_handling_context,
    stop_or_status_or_toggle,
)

LOGGER = logging.getLogger()

# LLM Prompts
SYSTEM_PROMPT = """\
You are a versatile AI text assistant. Your purpose is to either **modify** a given text or **answer questions** about it, based on a specific instruction.

- If the instruction is a **command to edit** the text (e.g., "make this more formal," "add emojis," "correct spelling"), you must return ONLY the full, modified text.
- If the instruction is a **question about** the text (e.g., "summarize this," "what are the key points?," "translate to French"), you must return ONLY the answer.

In all cases, you must follow these strict rules:
- Do not provide any explanations, apologies, or introductory phrases like "Here is the result:".
- Do not wrap your output in markdown or code blocks.
- Your output should be the direct result of the instruction: either the edited text or the answer to the question.
"""

AGENT_INSTRUCTIONS = """\
You will be given a block of text enclosed in <original-text> tags, and an instruction enclosed in <instruction> tags.
Analyze the instruction to determine if it's a command to edit the text or a question about it.

- If it is an editing command, apply the changes to the original text and return the complete, modified version.
- If it is a question, formulate an answer based on the original text.

Return ONLY the resulting text (either the edit or the answer), with no extra formatting or commentary.
"""


# --- Main Application Logic ---


async def _async_main(
    *,
    general_cfg: GeneralConfig,
    asr_config: ASRConfig,
    llm_config: LLMConfig,
    tts_config: TTSConfig,
    file_config: FileConfig,
) -> None:
    """Core asynchronous logic for the voice assistant."""
    with pyaudio_context() as p:
        device_info = setup_devices(p, general_cfg, asr_config, tts_config)
        if device_info is None:
            return
        input_device_index, _, tts_output_device_index = device_info
        asr_config.input_device_index = input_device_index
        tts_config.output_device_index = tts_output_device_index

        original_text = get_clipboard_text()
        if original_text is None:
            return

        if not general_cfg.quiet and original_text:
            print_input_panel(original_text, title="📝 Text to Process")

        with (
            signal_handling_context(LOGGER, general_cfg.quiet) as stop_event,
            maybe_live(not general_cfg.quiet) as live,
        ):
            audio_data = await asr.record_audio_with_manual_stop(
                p,
                input_device_index,
                stop_event,
                LOGGER,
                live=live,
                quiet=general_cfg.quiet,
            )

            if not audio_data:
                if not general_cfg.quiet:
                    print_with_style("No audio recorded", style="yellow")
                return

            instruction = await get_instruction_from_audio(
                audio_data=audio_data,
                asr_config=asr_config,
                llm_config=llm_config,
                logger=LOGGER,
                quiet=general_cfg.quiet,
            )
            if not instruction:
                return

            await process_instruction_and_respond(
                instruction=instruction,
                original_text=original_text,
                general_cfg=general_cfg,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
                system_prompt=SYSTEM_PROMPT,
                agent_instructions=AGENT_INSTRUCTIONS,
                live=live,
                logger=LOGGER,
            )


@app.command("voice-edit")
def voice_edit(
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
    # --- General Options ---
    save_file: Path | None = opts.SAVE_FILE,
    clipboard: bool = opts.CLIPBOARD,
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Interact with clipboard text via a voice command using local or remote services.

    Usage:
    - Run in foreground: agent-cli voice-edit --input-device-index 1
    - Run in background: agent-cli voice-edit --input-device-index 1 &
    - Check status: agent-cli voice-edit --status
    - Stop background process: agent-cli voice-edit --stop
    - List output devices: agent-cli voice-edit --list-output-devices
    - Save TTS to file: agent-cli voice-edit --tts --save-file response.wav
    """
    setup_logging(log_level, log_file, quiet=quiet)
    general_cfg = GeneralConfig(
        log_level=log_level,
        log_file=log_file,
        quiet=quiet,
        list_devices=list_devices,
        clipboard=clipboard,
    )
    process_name = "voice-edit"
    if stop_or_status_or_toggle(
        process_name,
        "voice assistant",
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

        file_config = FileConfig(save_file=save_file, history_dir=None, last_n_messages=0)

        asyncio.run(
            _async_main(
                general_cfg=general_cfg,
                asr_config=asr_config,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
            ),
        )
