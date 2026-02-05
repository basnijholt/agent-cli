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
import json
import logging
from contextlib import suppress
from pathlib import Path  # noqa: TC003

from agent_cli import config, opts
from agent_cli.agents._voice_agent_common import (
    get_instruction_from_audio,
    process_instruction_and_respond,
)
from agent_cli.cli import app
from agent_cli.core import process
from agent_cli.core.audio import setup_devices
from agent_cli.core.deps import requires_extras
from agent_cli.core.utils import (
    enable_json_mode,
    get_clipboard_text,
    maybe_live,
    print_command_line_args,
    print_input_panel,
    print_with_style,
    setup_logging,
    signal_handling_context,
    stop_or_status_or_toggle,
)
from agent_cli.services import asr

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
    provider_cfg: config.ProviderSelection,
    general_cfg: config.General,
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
) -> str | None:
    """Core asynchronous logic for the voice assistant."""
    device_info = setup_devices(general_cfg, audio_in_cfg, audio_out_cfg)
    if device_info is None:
        return None
    input_device_index, _, tts_output_device_index = device_info
    audio_in_cfg.input_device_index = input_device_index
    audio_out_cfg.output_device_index = tts_output_device_index

    original_text = get_clipboard_text()
    if original_text is None:
        return None

    if not general_cfg.quiet and original_text:
        print_input_panel(original_text, title="📝 Text to Process")

    with (
        signal_handling_context(LOGGER, general_cfg.quiet) as stop_event,
        maybe_live(not general_cfg.quiet) as live,
    ):
        audio_data = await asr.record_audio_with_manual_stop(
            input_device_index,
            stop_event,
            LOGGER,
            live=live,
            quiet=general_cfg.quiet,
        )

        if not audio_data:
            if not general_cfg.quiet:
                print_with_style("No audio recorded", style="yellow")
            return None

        instruction = await get_instruction_from_audio(
            audio_data=audio_data,
            provider_cfg=provider_cfg,
            audio_input_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            logger=LOGGER,
            quiet=general_cfg.quiet,
        )
        if not instruction:
            return None

        return await process_instruction_and_respond(
            instruction=instruction,
            original_text=original_text,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            audio_output_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
            system_prompt=SYSTEM_PROMPT,
            agent_instructions=AGENT_INSTRUCTIONS,
            live=live,
            logger=LOGGER,
        )


@app.command("voice-edit", rich_help_panel="Voice Commands")
@requires_extras("audio", "llm")
def voice_edit(
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
    # --- General Options ---
    save_file: Path | None = opts.SAVE_FILE,
    clipboard: bool = opts.CLIPBOARD,
    log_level: opts.LogLevel = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    list_devices: bool = opts.LIST_DEVICES,
    quiet: bool = opts.QUIET,
    json_output: bool = opts.JSON_OUTPUT,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Edit or query clipboard text using voice commands.

    **Workflow:** Captures clipboard text → records your voice command → transcribes
    it → sends both to an LLM → copies result back to clipboard.

    Use this for hands-free text editing (e.g., "make this more formal") or
    asking questions about clipboard content (e.g., "summarize this").

    **Typical hotkey integration:** Run `voice-edit &` on keypress to start
    recording, then send SIGINT (via `--stop`) on second keypress to process.

    **Examples:**

    - Basic usage: `agent-cli voice-edit`
    - With TTS response: `agent-cli voice-edit --tts`
    - Toggle on/off: `agent-cli voice-edit --toggle`
    - List audio devices: `agent-cli voice-edit --list-devices`
    """
    if print_args:
        print_command_line_args(locals())

    effective_quiet = quiet or json_output
    if json_output:
        enable_json_mode()

    setup_logging(log_level, log_file, quiet=effective_quiet)
    general_cfg = config.General(
        log_level=log_level,
        log_file=log_file,
        quiet=effective_quiet,
        list_devices=list_devices,
        clipboard=clipboard,
        save_file=save_file,
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

    with process.pid_file_context(process_name), suppress(KeyboardInterrupt):
        cfgs = config.create_provider_configs_from_locals(locals())

        result = asyncio.run(
            _async_main(
                provider_cfg=cfgs.provider,
                general_cfg=general_cfg,
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
        if json_output:
            print(json.dumps({"result": result}))
