"""Warm recorder daemon for low-latency transcription hotkeys."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import tempfile
import threading
import wave
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from agent_cli import config, constants, opts
from agent_cli.agents import transcribe as transcribe_agent
from agent_cli.core.audio import open_audio_stream, setup_devices, setup_input_stream
from agent_cli.core.process import PID_DIR
from agent_cli.core.utils import print_error_message, setup_logging

LOGGER = logging.getLogger(__name__)

DEFAULT_PREROLL_SECONDS = 0.5

app = typer.Typer(
    name="transcribe-recorder",
    help="Control a warm transcription recorder daemon.",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)


class WarmAudioBuffer:
    """Thread-safe audio buffer that preserves a small pre-roll window."""

    def __init__(self, *, max_preroll_chunks: int) -> None:
        """Create a buffer with a fixed number of pre-roll chunks."""
        self._preroll: deque[bytes] = deque(maxlen=max_preroll_chunks)
        self._recording_chunks: list[bytes] = []
        self._recording = False
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        """Return whether recording is currently active."""
        with self._lock:
            return self._recording

    def add_chunk(self, chunk: bytes) -> None:
        """Add one audio chunk from the warm input stream."""
        with self._lock:
            self._preroll.append(chunk)
            if self._recording:
                self._recording_chunks.append(chunk)

    def start(self) -> Literal["started", "already_recording"]:
        """Start retaining chunks, seeded with the current pre-roll."""
        with self._lock:
            if self._recording:
                return "already_recording"
            self._recording_chunks = list(self._preroll)
            self._recording = True
            return "started"

    def stop(self) -> bytes | None:
        """Stop retaining chunks and return the captured bytes."""
        with self._lock:
            if not self._recording:
                return None
            audio_data = b"".join(self._recording_chunks)
            self._recording_chunks = []
            self._recording = False
            return audio_data


@dataclass(frozen=True)
class TranscribeDaemonConfig:
    """Resolved transcribe configuration used by the daemon."""

    extra_instructions: str | None
    provider_cfg: config.ProviderSelection
    general_cfg: config.General
    audio_in_cfg: config.AudioInput
    wyoming_asr_cfg: config.WyomingASR
    openai_asr_cfg: config.OpenAIASR
    gemini_asr_cfg: config.GeminiASR
    ollama_cfg: config.Ollama
    openai_llm_cfg: config.OpenAILLM
    gemini_llm_cfg: config.GeminiLLM
    llm_enabled: bool
    transcription_log: Path | None
    save_recording: bool
    diarization_cfg: config.Diarization


def _option_default(option: Any) -> Any:
    return getattr(option, "default", option)


def _config_value(values: dict[str, Any], name: str, option: Any) -> Any:
    return values.get(name, _option_default(option))


def _load_daemon_config(config_file: str | None) -> TranscribeDaemonConfig:
    loaded_config = config.load_config(config_file)
    defaults = config.normalize_provider_defaults(loaded_config.get("defaults", {}))
    command_config = config.normalize_provider_defaults(loaded_config.get("transcribe", {}))
    values = {**defaults, **command_config}

    transcription_log = _config_value(values, "transcription_log", opts.TRANSCRIPTION_LOG)
    if transcription_log:
        transcription_log = Path(transcription_log).expanduser()

    return TranscribeDaemonConfig(
        extra_instructions=_config_value(values, "extra_instructions", None),
        provider_cfg=config.ProviderSelection(
            asr_provider=_config_value(values, "asr_provider", opts.ASR_PROVIDER),
            llm_provider=_config_value(values, "llm_provider", opts.LLM_PROVIDER),
            tts_provider="wyoming",
        ),
        general_cfg=config.General(
            log_level=_config_value(values, "log_level", opts.LOG_LEVEL),
            log_file=_config_value(values, "log_file", opts.LOG_FILE),
            quiet=True,
            list_devices=False,
            clipboard=False,
        ),
        audio_in_cfg=config.AudioInput(
            input_device_index=_config_value(values, "input_device_index", opts.INPUT_DEVICE_INDEX),
            input_device_name=_config_value(values, "input_device_name", opts.INPUT_DEVICE_NAME),
        ),
        wyoming_asr_cfg=config.WyomingASR(
            asr_wyoming_ip=_config_value(values, "asr_wyoming_ip", opts.ASR_WYOMING_IP),
            asr_wyoming_port=_config_value(values, "asr_wyoming_port", opts.ASR_WYOMING_PORT),
        ),
        openai_asr_cfg=config.OpenAIASR(
            asr_openai_model=_config_value(values, "asr_openai_model", opts.ASR_OPENAI_MODEL),
            openai_api_key=_config_value(values, "openai_api_key", opts.OPENAI_API_KEY),
            openai_base_url=_config_value(values, "asr_openai_base_url", opts.ASR_OPENAI_BASE_URL)
            or _config_value(values, "openai_base_url", opts.OPENAI_BASE_URL),
            asr_openai_prompt=_config_value(values, "asr_openai_prompt", opts.ASR_OPENAI_PROMPT),
        ),
        gemini_asr_cfg=config.GeminiASR(
            asr_gemini_model=_config_value(values, "asr_gemini_model", opts.ASR_GEMINI_MODEL),
            gemini_api_key=_config_value(values, "gemini_api_key", opts.GEMINI_API_KEY),
        ),
        ollama_cfg=config.Ollama(
            llm_ollama_model=_config_value(values, "llm_ollama_model", opts.LLM_OLLAMA_MODEL),
            llm_ollama_host=_config_value(values, "llm_ollama_host", opts.LLM_OLLAMA_HOST),
        ),
        openai_llm_cfg=config.OpenAILLM(
            llm_openai_model=_config_value(values, "llm_openai_model", opts.LLM_OPENAI_MODEL),
            openai_api_key=_config_value(values, "openai_api_key", opts.OPENAI_API_KEY),
            openai_base_url=_config_value(values, "openai_base_url", opts.OPENAI_BASE_URL),
        ),
        gemini_llm_cfg=config.GeminiLLM(
            llm_gemini_model=_config_value(values, "llm_gemini_model", opts.LLM_GEMINI_MODEL),
            gemini_api_key=_config_value(values, "gemini_api_key", opts.GEMINI_API_KEY),
        ),
        llm_enabled=bool(_config_value(values, "llm", opts.LLM)),
        transcription_log=transcription_log,
        save_recording=bool(_config_value(values, "save_recording", opts.SAVE_RECORDING)),
        diarization_cfg=config.Diarization(
            diarize=bool(_config_value(values, "diarize", opts.DIARIZE)),
            diarize_format=_config_value(values, "diarize_format", opts.DIARIZE_FORMAT),
            hf_token=_config_value(values, "hf_token", opts.HF_TOKEN),
            min_speakers=_config_value(values, "min_speakers", opts.MIN_SPEAKERS),
            max_speakers=_config_value(values, "max_speakers", opts.MAX_SPEAKERS),
            align_words=bool(_config_value(values, "align_words", opts.ALIGN_WORDS)),
            align_language=_config_value(values, "align_language", opts.ALIGN_LANGUAGE),
            enroll_speakers=_config_value(values, "enroll_speakers", opts.ENROLL_SPEAKERS),
            identify_speakers=bool(
                _config_value(values, "identify_speakers", opts.IDENTIFY_SPEAKERS)
            ),
            remember_unknown_speakers=bool(
                _config_value(values, "remember_unknown_speakers", opts.REMEMBER_UNKNOWN_SPEAKERS)
            ),
            speaker_profiles_file=Path(
                _config_value(values, "speaker_profiles_file", opts.SPEAKER_PROFILES_FILE)
            ).expanduser(),
            speaker_match_threshold=float(
                _config_value(values, "speaker_match_threshold", opts.SPEAKER_MATCH_THRESHOLD)
            ),
        ),
    )


def _socket_path(socket_path: Path | None = None) -> Path:
    if socket_path is not None:
        return socket_path.expanduser()
    return PID_DIR / "transcribe-recorder.sock"


def _recording_path(*, keep: bool) -> Path:
    if keep:
        directory = Path.home() / ".config" / "agent-cli" / "transcriptions"
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return directory / f"recording_{timestamp}.wav"
    with tempfile.NamedTemporaryFile(
        prefix="agent-cli-recording-",
        suffix=".wav",
        delete=False,
    ) as tmp:
        pass
    return Path(tmp.name)


def _write_wav(path: Path, audio_data: bytes) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(constants.AUDIO_CHANNELS)
        wav_file.setsampwidth(constants.AUDIO_FORMAT_WIDTH)
        wav_file.setframerate(constants.AUDIO_RATE)
        wav_file.writeframes(audio_data)


class WarmRecorder:
    """Owns the open input stream and continuously feeds a warm audio buffer."""

    def __init__(self, daemon_config: TranscribeDaemonConfig, *, preroll_seconds: float) -> None:
        """Create a recorder for one resolved daemon config."""
        self.daemon_config = daemon_config
        max_preroll_chunks = max(
            1,
            round(preroll_seconds * constants.AUDIO_RATE / constants.AUDIO_CHUNK_SIZE),
        )
        self.buffer = WarmAudioBuffer(max_preroll_chunks=max_preroll_chunks)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream_cm: Any = None
        self._stream: Any = None

    def open(self) -> None:
        """Open and start the input stream reader."""
        device_info = setup_devices(
            self.daemon_config.general_cfg, self.daemon_config.audio_in_cfg, None
        )
        if device_info is None:
            msg = "No input device selected"
            raise RuntimeError(msg)
        input_device_index, _, _ = device_info
        self.daemon_config.audio_in_cfg.input_device_index = input_device_index
        stream_config = setup_input_stream(input_device_index)
        self._stream_cm = open_audio_stream(stream_config)
        self._stream = self._stream_cm.__enter__()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="agent-cli-transcribe-recorder",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        """Close the input stream and stop the reader thread."""
        self._stop_event.set()
        if self._stream_cm is not None:
            self._stream_cm.__exit__(None, None, None)
            self._stream_cm = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, _overflow = self._stream.read(constants.AUDIO_CHUNK_SIZE)
            except Exception:
                if not self._stop_event.is_set():
                    LOGGER.exception("Warm recorder input stream failed")
                return
            self.buffer.add_chunk(data.tobytes())


class TranscribeDaemon:
    """Socket command handler around a warm recorder."""

    def __init__(
        self,
        *,
        config_file: str | None,
        preroll_seconds: float,
        socket_path: Path | None = None,
    ) -> None:
        """Load config and open the warm recorder."""
        self.config_file = config_file
        self.preroll_seconds = preroll_seconds
        self.socket_path = socket_path
        self.recorder = self._new_recorder()

    def _new_recorder(self) -> WarmRecorder:
        daemon_config = _load_daemon_config(self.config_file)
        setup_logging(
            daemon_config.general_cfg.log_level,
            daemon_config.general_cfg.log_file,
            quiet=True,
        )
        recorder = WarmRecorder(daemon_config, preroll_seconds=self.preroll_seconds)
        recorder.open()
        return recorder

    async def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle one socket request."""
        action = request.get("action")
        handlers = {
            "start": self.start,
            "status": self.status,
            "reload": self.reload,
        }
        if action in handlers:
            return handlers[action]()
        if action == "stop":
            return await self.stop()
        if action == "toggle":
            return await self.stop() if self.recorder.buffer.recording else self.start()
        return {"ok": False, "error": f"Unknown action: {action}"}

    def start(self) -> dict[str, Any]:
        """Start retaining audio."""
        state = self.recorder.buffer.start()
        return {"ok": True, "action": "start", "status": state}

    async def stop(self) -> dict[str, Any]:
        """Stop retaining audio and transcribe the captured buffer."""
        audio_data = self.recorder.buffer.stop()
        if audio_data is None:
            return {"ok": True, "action": "stop", "status": "not_recording"}
        if not audio_data:
            return {"ok": False, "action": "stop", "error": "No audio captured"}

        daemon_config = self.recorder.daemon_config
        recording_path = _recording_path(keep=daemon_config.save_recording)
        _write_wav(recording_path, audio_data)
        try:
            result = await transcribe_agent._async_main(
                audio_file_path=recording_path,
                extra_instructions=daemon_config.extra_instructions,
                provider_cfg=daemon_config.provider_cfg,
                general_cfg=daemon_config.general_cfg,
                wyoming_asr_cfg=daemon_config.wyoming_asr_cfg,
                openai_asr_cfg=daemon_config.openai_asr_cfg,
                gemini_asr_cfg=daemon_config.gemini_asr_cfg,
                ollama_cfg=daemon_config.ollama_cfg,
                openai_llm_cfg=daemon_config.openai_llm_cfg,
                gemini_llm_cfg=daemon_config.gemini_llm_cfg,
                llm_enabled=daemon_config.llm_enabled,
                transcription_log=daemon_config.transcription_log,
                save_recording=False,
                diarization_cfg=daemon_config.diarization_cfg,
                emit_output=False,
                raise_diarization_errors=daemon_config.diarization_cfg.diarize,
            )
        finally:
            if not daemon_config.save_recording:
                with suppress(OSError):
                    recording_path.unlink()
        return {
            "ok": True,
            "action": "stop",
            "status": "transcribed",
            "transcript": result.get("transcript"),
            "raw_transcript": result.get("raw_transcript"),
            "llm_enabled": result.get("llm_enabled", False),
            "recording_path": str(recording_path) if daemon_config.save_recording else None,
        }

    def reload(self) -> dict[str, Any]:
        """Reload config and reopen the warm input stream."""
        if self.recorder.buffer.recording:
            return {"ok": False, "action": "reload", "error": "Cannot reload while recording"}
        old_recorder = self.recorder
        new_recorder = self._new_recorder()
        self.recorder = new_recorder
        old_recorder.close()
        return {"ok": True, "action": "reload", "status": "reloaded"}

    def status(self) -> dict[str, Any]:
        """Return daemon status."""
        return {
            "ok": True,
            "action": "status",
            "recording": self.recorder.buffer.recording,
            "socket_path": str(self.socket_path or _socket_path()),
        }

    def close(self) -> None:
        """Close daemon resources."""
        self.recorder.close()


async def _serve(socket_path: Path, daemon: TranscribeDaemon) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(FileNotFoundError):
        await asyncio.to_thread(socket_path.unlink)

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await reader.readline()
            request = json.loads(raw.decode() or "{}")
            response = await daemon.handle(request)
        except Exception as exc:
            LOGGER.exception("Transcribe daemon request failed")
            response = {"ok": False, "error": str(exc)}
        writer.write(json.dumps(response).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=socket_path)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)
    try:
        async with server:
            await stop_event.wait()
    finally:
        server.close()
        await server.wait_closed()
        daemon.close()
        with suppress(FileNotFoundError):
            await asyncio.to_thread(socket_path.unlink)


async def _request(socket_path: Path, action: str) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    writer.write(json.dumps({"action": action}).encode() + b"\n")
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(raw.decode() or "{}")


def _print_response(response: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(response))
        return
    if not response.get("ok"):
        print_error_message("Transcribe daemon error", str(response.get("error", "Unknown error")))
        raise typer.Exit(1)
    transcript = response.get("transcript")
    if transcript:
        print(transcript)
    else:
        print(response.get("status", "ok"))


@app.command("serve")
def serve_cmd(
    config_file: Annotated[
        str | None,
        typer.Option("--config", help="Path to a TOML config file."),
    ] = None,
    socket_path: Annotated[
        Path | None,
        typer.Option("--socket", help="Unix socket path."),
    ] = None,
    preroll_seconds: Annotated[
        float,
        typer.Option("--pre-roll", min=0.0, help="Seconds of audio to keep before start."),
    ] = DEFAULT_PREROLL_SECONDS,
) -> None:
    """Run the warm recorder daemon in the foreground."""
    resolved_socket_path = _socket_path(socket_path)
    daemon = TranscribeDaemon(
        config_file=config_file,
        preroll_seconds=preroll_seconds,
        socket_path=resolved_socket_path,
    )
    asyncio.run(_serve(resolved_socket_path, daemon))


def _client_cmd(action: str, socket_path: Path | None, *, json_output: bool) -> None:
    path = _socket_path(socket_path)
    try:
        response = asyncio.run(_request(path, action))
    except (FileNotFoundError, ConnectionRefusedError):
        if json_output:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "Transcribe daemon is not running",
                        "socket_path": str(path),
                    },
                ),
            )
            raise typer.Exit(1) from None
        print_error_message("Transcribe daemon is not running", f"Socket not available: {path}")
        raise typer.Exit(1) from None
    _print_response(response, json_output=json_output)


@app.command("start")
def start_cmd(
    socket_path: Annotated[Path | None, typer.Option("--socket", help="Unix socket path.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON response.")] = False,
) -> None:
    """Start retaining audio from the warm recorder."""
    _client_cmd("start", socket_path, json_output=json_output)


@app.command("stop")
def stop_cmd(
    socket_path: Annotated[Path | None, typer.Option("--socket", help="Unix socket path.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON response.")] = False,
) -> None:
    """Stop recording and transcribe the captured audio."""
    _client_cmd("stop", socket_path, json_output=json_output)


@app.command("toggle")
def toggle_cmd(
    socket_path: Annotated[Path | None, typer.Option("--socket", help="Unix socket path.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON response.")] = False,
) -> None:
    """Start recording if idle, otherwise stop and transcribe."""
    _client_cmd("toggle", socket_path, json_output=json_output)


@app.command("status")
def status_cmd(
    socket_path: Annotated[Path | None, typer.Option("--socket", help="Unix socket path.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON response.")] = False,
) -> None:
    """Show daemon recording status."""
    _client_cmd("status", socket_path, json_output=json_output)


@app.command("reload")
def reload_cmd(
    socket_path: Annotated[Path | None, typer.Option("--socket", help="Unix socket path.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON response.")] = False,
) -> None:
    """Reload config and reopen the input stream."""
    _client_cmd("reload", socket_path, json_output=json_output)
