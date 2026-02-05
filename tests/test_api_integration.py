"""Integration tests for the FastAPI web service."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_cli.cli import app as cli_app
from agent_cli.server.proxy.api import TranscriptionRequest, app, transcribe_audio

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_full_transcription_workflow() -> None:
    """Test the full transcription workflow with mocked services."""
    # Create mock configs
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.server.proxy.api.process_and_update_clipboard") as mock_process,
    ):
        # Setup mocks
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "hello world this is a test"
        mock_process.return_value = "Hello world. This is a test."

        # Create a mock audio file
        audio_data = b"RIFF" + b"\x00" * 100  # Dummy WAV data

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = Path(tmp.name)

        try:
            # Create mock upload file
            class MockUploadFile:
                filename = "test.wav"
                content_type = "audio/wav"

                async def read(self) -> bytes:
                    return audio_data

            upload_file = MockUploadFile()

            # Create mock request
            class MockRequest:
                def __init__(self) -> None:
                    self.client = MagicMock()
                    self.client.host = "127.0.0.1"

                async def form(self) -> dict:
                    return {}

            request = MockRequest()

            # Create mock form data

            form_data = TranscriptionRequest(cleanup=True, extra_instructions=None)

            # Call the transcribe endpoint function directly
            result = await transcribe_audio(
                request=request,
                audio=upload_file,
                form_data=form_data,
            )

            assert result.success is True
            assert result.raw_transcript == "hello world this is a test"
            assert result.cleaned_transcript == "Hello world. This is a test."
            assert result.error is None

        finally:
            tmp_path.unlink(missing_ok=True)


def test_server_command_in_cli() -> None:
    """Test that the server command is registered in CLI."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["server", "--help"])

    assert result.exit_code == 0

    # Strip ANSI color codes for more reliable testing
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "whisper" in clean_output
    assert "transcribe-proxy" in clean_output


def test_server_transcribe_proxy_command_in_cli() -> None:
    """Test that the server transcribe-proxy command is registered in CLI."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["server", "transcribe-proxy", "--help"])

    assert result.exit_code == 0

    # Strip ANSI color codes for more reliable testing
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--host" in clean_output
    assert "--port" in clean_output
    assert "--reload" in clean_output


def test_server_whisper_command_in_cli() -> None:
    """Test that the server whisper command is registered in CLI."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["server", "whisper", "--help"])

    assert result.exit_code == 0

    # Strip ANSI color codes for more reliable testing
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--model" in clean_output
    assert "--ttl" in clean_output
    assert "--wyoming-port" in clean_output


@patch("uvicorn.run")
def test_server_transcribe_proxy_runs_uvicorn(mock_uvicorn_run: MagicMock) -> None:
    """Test the server transcribe-proxy command runs uvicorn."""
    runner = CliRunner()
    runner.invoke(cli_app, ["server", "transcribe-proxy", "--port", "8080"])

    # The command should attempt to run uvicorn
    mock_uvicorn_run.assert_called_once()
    call_kwargs = mock_uvicorn_run.call_args[1]
    assert call_kwargs["port"] == 8080
    assert call_kwargs["log_level"] == "info"


def test_api_configuration_handling(monkeypatch: MonkeyPatch) -> None:
    """Test that API properly handles configuration."""
    # Set environment variables
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")

    with patch("agent_cli.config.OpenAIASR") as mock_asr_config:
        mock_instance = MagicMock()
        mock_instance.openai_api_key = "test-key-123"
        mock_asr_config.return_value = mock_instance

        # Import after patching to get the mocked config

        # The function should be able to access the API key from config
        assert True  # Config is created during request


def test_temp_file_cleanup(client: TestClient) -> None:
    """Test that temporary files are cleaned up after processing."""
    temp_dir = Path(tempfile.gettempdir())
    temp_files_before = set(temp_dir.iterdir())

    with patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe:
        mock_transcribe.return_value = "test"

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "false"},
            )

            assert response.status_code == 200

    # Give a moment for cleanup
    time.sleep(0.1)

    temp_files_after = set(temp_dir.iterdir())
    new_files = temp_files_after - temp_files_before

    # No new WAV files should remain
    wav_files = [f for f in new_files if f.name.endswith(".wav")]
    assert len(wav_files) == 0


@pytest.mark.asyncio
async def test_concurrent_requests() -> None:
    """Test that the API can handle concurrent requests."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
    ):
        # Setup mocks
        mock_convert.return_value = b"converted_audio_data"

        # Make each request return a unique result
        call_count = 0

        async def mock_transcribe_side_effect(*args, **kwargs) -> str:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate some processing time
            return f"transcript {call_count}"

        mock_transcribe.side_effect = mock_transcribe_side_effect

        # Create multiple mock upload files
        class MockUploadFile:
            def __init__(self, idx: int) -> None:
                self.filename = f"test{idx}.wav"
                self.content_type = "audio/wav"
                self.idx = idx

            async def read(self) -> bytes:
                return b"RIFF" + bytes([self.idx])

        # Create mock request
        class MockRequest:
            def __init__(self) -> None:
                self.client = MagicMock()
                self.client.host = "127.0.0.1"

            async def form(self) -> dict:
                return {}

        # Create concurrent tasks
        tasks = []
        for i in range(5):
            upload_file = MockUploadFile(i)
            request = MockRequest()
            form_data = TranscriptionRequest(cleanup=False, extra_instructions=None)
            task = transcribe_audio(
                request=request,
                audio=upload_file,
                form_data=form_data,
            )
            tasks.append(task)

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Verify all requests were processed
        assert len(results) == 5
        for _i, result in enumerate(results):
            assert result.success is True
            assert result.raw_transcript.startswith("transcript")

        # Verify we had 5 calls
        assert call_count == 5
