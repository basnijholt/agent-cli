"""Tests for the FastAPI web service."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_cli.api import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"


def test_transcribe_no_file(client: TestClient) -> None:
    """Test transcription endpoint without a file."""
    response = client.post("/transcribe")
    assert response.status_code == 422  # Unprocessable Entity


def test_transcribe_invalid_file_type(client: TestClient) -> None:
    """Test transcription endpoint with invalid file type."""
    with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
        tmp.write(b"This is not an audio file")
        tmp.seek(0)
        response = client.post(
            "/transcribe",
            files={"audio": ("test.txt", tmp, "text/plain")},
        )
    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]


@patch("agent_cli.server.proxy.api._build_context_payload")
@patch("agent_cli.server.proxy.api.get_default_logger")
@patch("agent_cli.server.proxy.api.process_and_update_clipboard")
@patch("agent_cli.server.proxy.api._transcribe_with_provider")
@patch("agent_cli.server.proxy.api._convert_audio_for_local_asr")
def test_transcribe_success_with_cleanup(
    mock_convert: AsyncMock,
    mock_transcribe: AsyncMock,
    mock_process: AsyncMock,
    mock_get_logger: MagicMock,
    mock_context_builder: MagicMock,
    client: TestClient,
) -> None:
    """Test successful transcription with cleanup."""
    # Mock the audio conversion, transcription and cleanup
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.return_value = "this is a test transcription"
    mock_process.return_value = "This is a test transcription."
    mock_context_builder.return_value = (None, None)
    mock_logger = MagicMock()
    mock_logger.log_file = Path("test-log.jsonl")
    mock_get_logger.return_value = mock_logger

    # Create a dummy audio file
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(b"RIFF")  # Minimal WAV header
        tmp.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", tmp, "audio/wav")},
            data={"cleanup": "true"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["raw_transcript"] == "this is a test transcription"
    assert data["cleaned_transcript"] == "This is a test transcription."
    assert data["error"] is None

    # Verify mocks were called
    mock_convert.assert_called_once()
    mock_transcribe.assert_called_once()
    mock_process.assert_called_once()
    mock_context_builder.assert_called_once()


@patch("agent_cli.server.proxy.api._convert_audio_for_local_asr")
@patch("agent_cli.server.proxy.api._transcribe_with_provider")
def test_transcribe_success_without_cleanup(
    mock_transcribe: AsyncMock,
    mock_convert: AsyncMock,
    client: TestClient,
) -> None:
    """Test successful transcription without cleanup."""
    # Mock the audio conversion and transcription
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.return_value = "this is a test transcription"

    # Create a dummy audio file
    with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
        tmp.write(b"ID3")  # Minimal MP3 header
        tmp.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.mp3", tmp, "audio/mpeg")},
            data={"cleanup": "false"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["raw_transcript"] == "this is a test transcription"
    assert data["cleaned_transcript"] is None
    assert data["error"] is None

    # Verify mocks were called
    mock_convert.assert_called_once()
    mock_transcribe.assert_called_once()


@patch("agent_cli.server.proxy.api._convert_audio_for_local_asr")
@patch("agent_cli.server.proxy.api._transcribe_with_provider")
def test_transcribe_empty_result(
    mock_transcribe: AsyncMock,
    mock_convert: AsyncMock,
    client: TestClient,
) -> None:
    """Test transcription with empty result."""
    # Mock audio conversion and empty transcription
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.return_value = ""

    with tempfile.NamedTemporaryFile(suffix=".m4a") as tmp:
        tmp.write(b"ftyp")  # Minimal M4A header
        tmp.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.m4a", tmp, "audio/mp4")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["raw_transcript"] == ""
    assert data["error"] == "No transcript generated from audio"


@patch("agent_cli.server.proxy.api._convert_audio_for_local_asr")
@patch("agent_cli.server.proxy.api._transcribe_with_provider")
def test_transcribe_with_exception(
    mock_transcribe: AsyncMock,
    mock_convert: AsyncMock,
    client: TestClient,
) -> None:
    """Test transcription with exception."""
    # Mock audio conversion and exception during transcription
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.side_effect = Exception("API Error: Invalid API key")

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(b"RIFF")
        tmp.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", tmp, "audio/wav")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["raw_transcript"] == ""
    assert "API Error: Invalid API key" in data["error"]


def test_transcribe_with_extra_instructions(client: TestClient) -> None:
    """Test transcription with extra instructions."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.server.proxy.api.process_and_update_clipboard") as mock_process,
    ):
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "hello world"
        mock_process.return_value = "Hello, World!"

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={
                    "cleanup": "true",
                    "extra_instructions": "Add proper punctuation and capitalize appropriately.",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Check that extra instructions were passed to the cleanup function
        call_args = mock_process.call_args
        assert "Add proper punctuation" in call_args.kwargs["agent_instructions"]


def test_string_boolean_cleanup(client: TestClient) -> None:
    """Test that cleanup parameter accepts string 'true'/'false' for iOS compatibility."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.server.proxy.api.process_and_update_clipboard") as mock_process,
    ):
        mock_process.return_value = "This is a test transcription."
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "test transcription"

        # Test with string "true"
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "true"},  # String instead of boolean
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

        # Test with string "false"
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "false"},  # String instead of boolean
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["cleaned_transcript"] is None  # No cleanup when false


def test_early_exception_no_crash(client: TestClient) -> None:
    """Test that early exceptions don't crash the server due to uninitialized variables."""
    # Test with no audio file at all - should fail early but not crash
    response = client.post("/transcribe", data={"cleanup": "true"})
    assert response.status_code == 422  # Unprocessable Entity

    # Server should still be responsive after the error
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "healthy"


def test_logging_failure_no_crash(client: TestClient) -> None:
    """Test that logging failures in finally block don't crash the server."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.server.proxy.api.get_default_logger") as mock_logger,
    ):
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "test transcription"

        # Make the logger raise an exception
        mock_logger.side_effect = OSError("Cannot write to log file")

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "false"},
            )

            # Should return success despite logging failure
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["raw_transcript"] == "test transcription"

    # Server should still be responsive
    health_response = client.get("/health")
    assert health_response.status_code == 200


def test_exception_with_partial_processing(client: TestClient) -> None:
    """Test handling when exception occurs after partial processing."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.server.proxy.api.process_and_update_clipboard") as mock_process,
    ):
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "test transcription"
        # Make cleanup processing fail
        mock_process.side_effect = Exception("LLM service unavailable")

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "true"},  # Request cleanup which will fail
            )

            # Should handle the error gracefully
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "LLM service unavailable" in data["error"]
            assert data["raw_transcript"] == ""  # Reset on error


def test_llm_connection_error_no_server_exit(client: TestClient) -> None:
    """Test that LLM connection errors don't cause server to exit."""
    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.services.llm.create_llm_agent") as mock_create_agent,
    ):
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "test transcription"

        # Mock the agent to raise a connection error
        mock_agent = AsyncMock()
        mock_agent.run.side_effect = Exception("Connection error")
        mock_create_agent.return_value = mock_agent

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(b"RIFF")
            tmp.seek(0)

            response = client.post(
                "/transcribe",
                files={"audio": ("test.wav", tmp, "audio/wav")},
                data={"cleanup": "true"},
            )

            # Should return partial success (transcription worked, cleanup failed)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True  # Transcription succeeded
            assert data["raw_transcript"] == "test transcription"
            assert data["cleaned_transcript"] is None  # Cleanup failed
            assert "cleanup failed" in data["error"].lower()

    # Server should still be responsive after LLM error
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "healthy"


def test_supported_audio_formats(client: TestClient) -> None:
    """Test all supported audio formats."""
    supported_formats = [
        (".wav", b"RIFF", "audio/wav"),
        (".mp3", b"ID3", "audio/mpeg"),
        (".m4a", b"ftyp", "audio/mp4"),
        (".flac", b"fLaC", "audio/flac"),
        (".ogg", b"OggS", "audio/ogg"),
        (".aac", b"\xff\xf1", "audio/aac"),
    ]

    with (
        patch("agent_cli.server.proxy.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.server.proxy.api._transcribe_with_provider") as mock_transcribe,
    ):
        mock_convert.return_value = b"converted_audio_data"
        mock_transcribe.return_value = "test"

        for ext, header, mime_type in supported_formats:
            with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
                tmp.write(header)
                tmp.seek(0)

                response = client.post(
                    "/transcribe",
                    files={"audio": (f"test{ext}", tmp, mime_type)},
                    data={"cleanup": "false"},
                )

                assert response.status_code == 200, f"Failed for {ext}"
                data = response.json()
                assert data["success"] is True, f"Failed for {ext}"


@patch("agent_cli.server.proxy.api._build_context_payload")
@patch("agent_cli.server.proxy.api.get_default_logger")
@patch("agent_cli.server.proxy.api.process_and_update_clipboard")
@patch("agent_cli.server.proxy.api._transcribe_with_provider")
@patch("agent_cli.server.proxy.api._convert_audio_for_local_asr")
def test_transcribe_cleanup_includes_context(
    mock_convert: AsyncMock,
    mock_transcribe: AsyncMock,
    mock_process: AsyncMock,
    mock_get_logger: MagicMock,
    mock_context_builder: MagicMock,
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Ensure cleanup context includes recent log snippets when available."""
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.return_value = "context example"
    mock_process.return_value = "Context Example"
    mock_context_builder.return_value = ("Recent transcript history...", "note")
    mock_logger = MagicMock()
    mock_logger.log_file = tmp_path / "api-log.jsonl"
    mock_get_logger.return_value = mock_logger

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(b"RIFF")
        tmp.seek(0)
        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", tmp, "audio/wav")},
            data={"cleanup": "true"},
        )

    assert response.status_code == 200
    mock_context_builder.assert_called_once_with(
        transcription_log=mock_logger.log_file,
        clipboard_snapshot=None,
    )
    kwargs = mock_process.call_args.kwargs
    assert kwargs["context"] == "Recent transcript history..."
    mock_logger.log_transcription.assert_called_once_with(
        raw="context example",
        processed="Context Example",
    )
