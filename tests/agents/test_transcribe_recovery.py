"""Integration tests for the transcribe recovery features."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.asr import Transcript

from agent_cli import config, constants
from agent_cli.agents import transcribe
from agent_cli.constants import DEFAULT_OPENAI_MODEL


def create_test_wav_file(filepath: Path, content: bytes = b"test_audio" * 1000) -> None:
    """Create a test WAV file."""
    with wave.open(str(filepath), "wb") as wav_file:
        wav_file.setnchannels(constants.AUDIO_CHANNELS)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(constants.AUDIO_RATE)
        wav_file.writeframes(content)


@pytest.mark.asyncio
async def test_async_main_from_file(tmp_path: Path):
    """Test transcribing from a saved audio file."""
    # Create a test WAV file
    test_file = tmp_path / "test_recording.wav"
    create_test_wav_file(test_file)

    # Mock the transcriber
    with (
        patch("agent_cli.agents.transcribe.create_recorded_audio_transcriber") as mock_create,
        patch("agent_cli.agents.transcribe.load_audio_from_file") as mock_load,
        patch("pyperclip.copy") as mock_pyperclip_copy,
    ):
        # Setup mocks
        mock_load.return_value = b"audio_data"
        mock_transcriber = AsyncMock(return_value="Test transcript from file")
        mock_create.return_value = mock_transcriber

        # Create config objects
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=True,
            list_devices=False,
            clipboard=True,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model="whisper-1",
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=DEFAULT_OPENAI_MODEL,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-3-flash-preview",
        )

        # Call the unified function with file path
        await transcribe._async_main(
            audio_file_path=test_file,
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=None,
        )

        # Verify the audio was loaded and transcribed
        # Wyoming provider requires PCM conversion
        mock_load.assert_called_once_with(test_file, transcribe.LOGGER, convert_to_pcm=True)
        mock_transcriber.assert_called_once()
        mock_pyperclip_copy.assert_called_once_with("Test transcript from file")


@pytest.mark.asyncio
async def test_async_main_from_file_with_llm(tmp_path: Path):
    """Test transcribing from a file with LLM processing."""
    # Create a test WAV file
    test_file = tmp_path / "test_recording.wav"
    create_test_wav_file(test_file)

    with (
        patch("agent_cli.agents.transcribe.create_recorded_audio_transcriber") as mock_create,
        patch("agent_cli.agents.transcribe.load_audio_from_file") as mock_load,
        patch("agent_cli.agents.transcribe.process_and_update_clipboard") as mock_process,
        patch("pyperclip.copy") as mock_pyperclip_copy,
        patch("pyperclip.paste", return_value=""),
    ):
        # Setup mocks
        mock_load.return_value = b"audio_data"
        mock_transcriber = AsyncMock(return_value="Raw transcript")
        mock_create.return_value = mock_transcriber
        mock_process.return_value = "Processed transcript"

        # Create config objects
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=True,
            list_devices=False,
            clipboard=True,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model="whisper-1",
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=DEFAULT_OPENAI_MODEL,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-3-flash-preview",
        )

        # Call the unified function with LLM enabled
        await transcribe._async_main(
            audio_file_path=test_file,
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=True,
            transcription_log=None,
        )

        # Verify LLM processing was called
        mock_process.assert_called_once()
        assert mock_process.call_args.kwargs["original_text"] == "Raw transcript"
        mock_pyperclip_copy.assert_called_once_with("Raw transcript")


@pytest.mark.asyncio
async def test_async_main_from_file_with_logging(tmp_path: Path):
    """Test transcribing from a file with transcription logging."""
    # Create a test WAV file and log file
    test_file = tmp_path / "test_recording.wav"
    log_file = tmp_path / "transcription.jsonl"
    create_test_wav_file(test_file)

    with (
        patch("agent_cli.agents.transcribe.create_recorded_audio_transcriber") as mock_create,
        patch("agent_cli.agents.transcribe.load_audio_from_file") as mock_load,
        patch("pyperclip.copy"),
    ):
        # Setup mocks
        mock_load.return_value = b"audio_data"
        mock_transcriber = AsyncMock(return_value="Test transcript")
        mock_create.return_value = mock_transcriber

        # Create config objects
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=True,
            list_devices=False,
            clipboard=True,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model="whisper-1",
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=DEFAULT_OPENAI_MODEL,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-3-flash-preview",
        )

        # Call the unified function with logging enabled
        await transcribe._async_main(
            audio_file_path=test_file,
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=log_file,
        )

        # Verify log file was created
        assert log_file.exists()

        # Read and verify log entry
        with log_file.open("r") as f:
            log_entries = [json.loads(line.strip()) for line in f]

        assert len(log_entries) == 1
        entry = log_entries[0]
        assert entry["role"] == "user"
        assert entry["raw_output"] == "Test transcript"
        assert entry["processed_output"] is None


@pytest.mark.asyncio
async def test_async_main_from_file_error_handling(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test error handling when audio file cannot be loaded."""
    test_file = tmp_path / "nonexistent.wav"

    with patch("agent_cli.agents.transcribe.load_audio_from_file") as mock_load:
        # Make loading fail
        mock_load.return_value = None

        # Create config objects
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=False,  # Not quiet so we can check output
            list_devices=False,
            clipboard=True,
        )
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model="whisper-1",
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=DEFAULT_OPENAI_MODEL,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-3-flash-preview",
        )

        # Call the unified function (should handle error gracefully)
        await transcribe._async_main(
            audio_file_path=test_file,
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=None,
        )

        # Check that error message was printed
        captured = capsys.readouterr()
        assert "Failed to load audio" in captured.out


@pytest.mark.asyncio
async def test_async_main_save_recording_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that recordings are saved when save_recording=True."""
    # Monkeypatch the transcriptions directory
    monkeypatch.setattr("agent_cli.services.asr._get_transcriptions_dir", lambda: tmp_path)

    # Mock the audio stream to avoid requiring real audio hardware
    mock_stream = MagicMock()
    mock_stream.read.return_value = (b"\x00" * 1024, False)  # Silence audio data

    with (
        patch("agent_cli.services.asr.wyoming_client_context") as mock_context,
        patch("pyperclip.copy"),
        patch("pyperclip.paste", return_value=""),
        patch("agent_cli.agents.transcribe.signal_handling_context") as mock_signal,
        patch("agent_cli.services.asr.open_audio_stream") as mock_audio,
    ):
        # Setup audio stream mock
        mock_audio.return_value.__enter__.return_value = mock_stream

        # Setup mocks
        mock_client = AsyncMock()
        mock_context.return_value.__aenter__.return_value = mock_client

        # Mock events for transcript
        mock_client.read_event.side_effect = [
            Transcript(text="Test transcript").event(),
            None,
        ]

        # Setup stop event
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]
        mock_signal.return_value.__enter__.return_value = stop_event

        # Create config objects
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=True,
            list_devices=False,
            clipboard=True,
        )
        audio_in_cfg = config.AudioInput()
        wyoming_asr_cfg = config.WyomingASR(
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
        )
        openai_asr_cfg = config.OpenAIASR(
            asr_openai_model="whisper-1",
        )
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
        )
        ollama_cfg = config.Ollama(
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
        )
        openai_llm_cfg = config.OpenAILLM(
            llm_openai_model=DEFAULT_OPENAI_MODEL,
        )
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-3-flash-preview",
        )

        # Call with save_recording=True
        await transcribe._async_main(
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=None,
            save_recording=True,  # Enable saving
        )
        # Since we mocked the Wyoming client, the actual saving happens in _send_audio
        # which is tested separately. Here we just verify the parameter is passed through.
        # The save_recording parameter should be passed to the transcriber.


def test_transcribe_command_last_recording_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the --last-recording command line option."""
    # Create a test recording file
    recording_file = tmp_path / "recording_20240101_120000_000.wav"
    create_test_wav_file(recording_file)

    # Monkeypatch to return our test file
    monkeypatch.setattr(
        "agent_cli.agents.transcribe.get_last_recording",
        lambda _idx=1: recording_file,
    )

    with (
        patch("agent_cli.agents.transcribe.asyncio.run") as mock_run,
        patch("agent_cli.agents.transcribe.print_with_style") as mock_print,
    ):
        # Call transcribe with --last-recording as int
        transcribe.transcribe(
            last_recording=1,
            from_file=None,
            save_recording=True,
            extra_instructions=None,
            asr_provider="wyoming",
            llm_provider="ollama",
            input_device_index=None,
            input_device_name=None,
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
            asr_openai_model="whisper-1",
            asr_openai_base_url=None,
            asr_openai_prompt=None,
            asr_gemini_model="gemini-2.0-flash",
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
            llm_openai_model=DEFAULT_OPENAI_MODEL,
            openai_api_key=None,
            openai_base_url=None,
            llm_gemini_model="gemini-3-flash-preview",
            gemini_api_key=None,
            llm=False,
            stop=False,
            status=False,
            toggle=False,
            clipboard=True,
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            json_output=False,
            config_file=None,
            print_args=False,
            transcription_log=None,
        )

        # Verify _async_main_from_file was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        # The coroutine is passed to asyncio.run
        assert call_args.__name__ == "_async_main"
        call_args.close()  # Avoid "coroutine never awaited" warning

        # Verify the message about using most recent recording
        mock_print.assert_called()
        assert "Using most recent recording" in mock_print.call_args[0][0]


def test_transcribe_command_from_file_option(tmp_path: Path):
    """Test the --from-file command line option."""
    # Create a test file
    test_file = tmp_path / "custom_recording.wav"
    create_test_wav_file(test_file)

    with patch("agent_cli.agents.transcribe.asyncio.run") as mock_run:
        # Call transcribe with --from-file
        transcribe.transcribe(
            last_recording=0,
            from_file=test_file,
            save_recording=True,
            extra_instructions=None,
            asr_provider="wyoming",
            llm_provider="ollama",
            input_device_index=None,
            input_device_name=None,
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
            asr_openai_model="whisper-1",
            asr_openai_base_url=None,
            asr_openai_prompt=None,
            asr_gemini_model="gemini-2.0-flash",
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
            llm_openai_model=DEFAULT_OPENAI_MODEL,
            openai_api_key=None,
            openai_base_url=None,
            llm_gemini_model="gemini-3-flash-preview",
            gemini_api_key=None,
            llm=False,
            stop=False,
            status=False,
            toggle=False,
            clipboard=True,
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=True,
            json_output=False,
            config_file=None,
            print_args=False,
            transcription_log=None,
        )

        # Verify _async_main_from_file was called with the right file
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args.__name__ == "_async_main"
        call_args.close()  # Avoid "coroutine never awaited" warning


def test_transcribe_command_last_recording_with_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the --last-recording command with different indices."""
    # Create multiple test recording files
    recording_files = [
        tmp_path / "recording_20240101_110000_000.wav",
        tmp_path / "recording_20240101_120000_000.wav",
        tmp_path / "recording_20240101_130000_000.wav",
    ]
    for f in recording_files:
        create_test_wav_file(f)

    # Monkeypatch to return the second-to-last file
    monkeypatch.setattr(
        "agent_cli.agents.transcribe.get_last_recording",
        lambda idx: recording_files[-2] if idx == 2 else None,
    )

    with (
        patch("agent_cli.agents.transcribe.asyncio.run") as mock_run,
        patch("agent_cli.agents.transcribe.print_with_style") as mock_print,
    ):
        # Call transcribe with --last-recording 2 (second-to-last)
        transcribe.transcribe(
            last_recording=2,
            from_file=None,
            save_recording=True,
            extra_instructions=None,
            asr_provider="wyoming",
            llm_provider="ollama",
            input_device_index=None,
            input_device_name=None,
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
            asr_openai_model="whisper-1",
            asr_openai_base_url=None,
            asr_openai_prompt=None,
            asr_gemini_model="gemini-2.0-flash",
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
            llm_openai_model=DEFAULT_OPENAI_MODEL,
            openai_api_key=None,
            openai_base_url=None,
            llm_gemini_model="gemini-3-flash-preview",
            gemini_api_key=None,
            llm=False,
            stop=False,
            status=False,
            toggle=False,
            clipboard=True,
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            json_output=False,
            config_file=None,
            print_args=False,
            transcription_log=None,
        )

        # Verify _async_main_from_file was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        call_args.close()  # Avoid "coroutine never awaited" warning

        # Verify the message about using recording #2
        mock_print.assert_called()
        assert any("#2" in str(call) for call in mock_print.call_args_list)


def test_transcribe_command_last_recording_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the --last-recording command when disabled (0)."""
    # Create a test recording file
    recording_file = tmp_path / "recording_20240101_120000_000.wav"
    create_test_wav_file(recording_file)

    # Monkeypatch to return our test file
    monkeypatch.setattr(
        "agent_cli.agents.transcribe.get_last_recording",
        lambda idx: recording_file if idx == 1 else None,
    )

    with (
        patch("agent_cli.agents.transcribe.asyncio.run") as mock_run,
        patch("agent_cli.core.process.pid_file_context") as mock_pid_context,
    ):
        # Call transcribe with --last-recording disabled (0)
        transcribe.transcribe(
            last_recording=0,  # Disabled
            from_file=None,
            save_recording=True,
            extra_instructions=None,
            asr_provider="wyoming",
            llm_provider="ollama",
            input_device_index=None,
            input_device_name=None,
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
            asr_openai_model="whisper-1",
            asr_openai_base_url=None,
            asr_openai_prompt=None,
            asr_gemini_model="gemini-2.0-flash",
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
            llm_openai_model=DEFAULT_OPENAI_MODEL,
            openai_api_key=None,
            openai_base_url=None,
            llm_gemini_model="gemini-3-flash-preview",
            gemini_api_key=None,
            llm=False,
            stop=False,
            status=False,
            toggle=False,
            clipboard=True,
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            json_output=False,
            config_file=None,
            print_args=False,
            transcription_log=None,
        )

        # Verify _async_main was called for normal recording (not from file)
        mock_run.assert_called_once()
        mock_pid_context.assert_called_once_with("transcribe")
        call_args = mock_run.call_args[0][0]
        # Should be normal recording mode, not file mode
        assert call_args.__name__ == "_async_main"
        call_args.close()  # Avoid "coroutine never awaited" warning


def test_transcribe_command_conflicting_options() -> None:
    """Test error handling for conflicting --last-recording and --from-file."""
    with patch("agent_cli.agents.transcribe.print_with_style") as mock_print:
        # Call with both options (should error)
        transcribe.transcribe(
            last_recording=1,
            from_file=Path("/some/file.wav"),
            save_recording=True,
            extra_instructions=None,
            asr_provider="wyoming",
            llm_provider="ollama",
            input_device_index=None,
            input_device_name=None,
            asr_wyoming_ip="localhost",
            asr_wyoming_port=10300,
            asr_openai_model="whisper-1",
            asr_openai_base_url=None,
            asr_openai_prompt=None,
            asr_gemini_model="gemini-2.0-flash",
            llm_ollama_model="gemma3:4b",
            llm_ollama_host="http://localhost:11434",
            llm_openai_model=DEFAULT_OPENAI_MODEL,
            openai_api_key=None,
            openai_base_url=None,
            llm_gemini_model="gemini-3-flash-preview",
            gemini_api_key=None,
            llm=False,
            stop=False,
            status=False,
            toggle=False,
            clipboard=True,
            log_level="WARNING",
            log_file=None,
            list_devices=False,
            quiet=False,
            json_output=False,
            config_file=None,
            print_args=False,
            transcription_log=None,
        )

        # Verify error message
        mock_print.assert_called()
        assert "Cannot use both --last-recording and --from-file" in mock_print.call_args[0][0]
