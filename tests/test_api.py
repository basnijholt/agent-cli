"""Tests for the FastAPI web service."""

from __future__ import annotations

import tempfile
from unittest.mock import AsyncMock, patch

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


@patch("agent_cli.api._convert_audio_for_local_asr")
@patch("agent_cli.api._transcribe_with_provider")
@patch("agent_cli.api.process_and_update_clipboard")
def test_transcribe_success_with_cleanup(
    mock_process: AsyncMock,
    mock_transcribe: AsyncMock,
    mock_convert: AsyncMock,
    client: TestClient,
) -> None:
    """Test successful transcription with cleanup."""
    # Mock the audio conversion, transcription and cleanup
    mock_convert.return_value = b"converted_audio_data"
    mock_transcribe.return_value = "this is a test transcription"
    mock_process.return_value = "This is a test transcription."

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


@patch("agent_cli.api._convert_audio_for_local_asr")
@patch("agent_cli.api._transcribe_with_provider")
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


@patch("agent_cli.api._convert_audio_for_local_asr")
@patch("agent_cli.api._transcribe_with_provider")
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


@patch("agent_cli.api._convert_audio_for_local_asr")
@patch("agent_cli.api._transcribe_with_provider")
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
        patch("agent_cli.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.api.process_and_update_clipboard") as mock_process,
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
        patch("agent_cli.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.api._transcribe_with_provider") as mock_transcribe,
        patch("agent_cli.api.process_and_update_clipboard") as mock_process,
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
        patch("agent_cli.api._convert_audio_for_local_asr") as mock_convert,
        patch("agent_cli.api._transcribe_with_provider") as mock_transcribe,
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
