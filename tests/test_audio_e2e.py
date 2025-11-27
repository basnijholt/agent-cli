"""End-to-end tests for the audio module with minimal mocking."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from agent_cli.core import audio


@pytest.fixture(autouse=True)
def _mock_sd_query_devices_with_cache_clear() -> None:
    """Clear the audio device cache before each test."""
    audio._get_all_devices.cache_clear()


@patch("sounddevice.query_devices")
def test_get_all_devices_caching(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test that device enumeration is cached for performance."""
    mock_query_devices.return_value = mock_audio_device_info

    # First call should hit query_devices
    devices1 = audio._get_all_devices()

    # Second call should use cached results
    devices2 = audio._get_all_devices()

    # Results should be identical
    assert devices1 == devices2
    assert len(devices1) == len(mock_audio_device_info)

    # Check call count - should be called once due to cache
    mock_query_devices.assert_called_once()


@patch("sounddevice.query_devices")
def test_list_input_devices(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test listing input devices."""
    mock_query_devices.return_value = mock_audio_device_info
    audio._list_input_devices()


@patch("sounddevice.query_devices")
def test_list_output_devices(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test listing output devices."""
    mock_query_devices.return_value = mock_audio_device_info
    audio._list_output_devices()


@patch("sounddevice.query_devices")
def test_list_all_devices(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test listing all audio devices."""
    mock_query_devices.return_value = mock_audio_device_info
    audio.list_all_devices()


@patch("sounddevice.query_devices")
def test_input_device_by_index(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test selecting input device by index."""
    mock_query_devices.return_value = mock_audio_device_info

    input_device_index, input_device_name = audio._input_device(
        input_device_name=None,
        input_device_index=0,
    )

    expected_device = next(dev for dev in mock_audio_device_info if dev["max_input_channels"] > 0)

    assert input_device_name == expected_device["name"]
    assert input_device_index == expected_device["index"]


@patch("sounddevice.query_devices")
def test_input_device_by_name(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test selecting input device by name."""
    mock_query_devices.return_value = mock_audio_device_info

    input_device = next(dev for dev in mock_audio_device_info if dev["max_input_channels"] > 0)

    input_device_index, input_device_name = audio._input_device(
        input_device_name=input_device["name"],
        input_device_index=None,
    )

    assert input_device_name == input_device["name"]
    assert input_device_index == input_device["index"]


@patch("sounddevice.query_devices")
def test_output_device_by_index(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test selecting output device by index."""
    mock_query_devices.return_value = mock_audio_device_info

    input_device_index, input_device_name = audio._output_device(
        input_device_name=None,
        input_device_index=1,
    )

    expected_device = next(
        dev
        for dev in mock_audio_device_info
        if dev["index"] == 1 and dev["max_output_channels"] > 0
    )

    assert input_device_name == expected_device["name"]
    assert input_device_index == expected_device["index"]


@patch("sounddevice.query_devices")
def test_output_device_by_name(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test selecting output device by name."""
    mock_query_devices.return_value = mock_audio_device_info

    output_device = next(dev for dev in mock_audio_device_info if dev["max_output_channels"] > 0)

    input_device_index, input_device_name = audio._output_device(
        input_device_name=output_device["name"],
        input_device_index=None,
    )

    assert input_device_name == output_device["name"]
    assert input_device_index == output_device["index"]


@patch("sounddevice.query_devices")
def test_input_device_invalid_index(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test error handling for invalid device index."""
    mock_query_devices.return_value = mock_audio_device_info

    with pytest.raises(ValueError, match="Device index 999 not found"):
        audio._input_device(
            input_device_name=None,
            input_device_index=999,
        )


@patch("sounddevice.query_devices")
def test_input_device_invalid_name(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test error handling for invalid device name."""
    mock_query_devices.return_value = mock_audio_device_info

    with pytest.raises(ValueError, match="No input device found"):
        audio._input_device(
            input_device_name="NonExistentDevice",
            input_device_index=None,
        )


@patch("sounddevice.query_devices")
def test_output_device_invalid_name(
    mock_query_devices: Mock,
    mock_audio_device_info: list[dict],
) -> None:
    """Test error handling for invalid output device name."""
    mock_query_devices.return_value = mock_audio_device_info

    with pytest.raises(ValueError, match="No output device found"):
        audio._output_device(
            input_device_name="NonExistentOutputDevice",
            input_device_index=None,
        )


@patch("sounddevice.InputStream")
@patch("sounddevice.OutputStream")
def test_open_audio_stream_context_manager(
    mock_output_stream: Mock,
    mock_input_stream: Mock,
) -> None:
    """Test open_audio_stream context manager."""
    # Test input stream
    input_config = audio.StreamConfig(
        rate=16000,
        channels=1,
        dtype="int16",
        device=0,
        blocksize=1024,
        kind="input",
    )
    with audio.open_audio_stream(input_config) as stream:
        assert stream is not None
        mock_input_stream.assert_called()

    # Test output stream
    output_config = audio.StreamConfig(
        rate=24000,
        channels=1,
        dtype="int16",
        device=1,
        blocksize=1024,
        kind="output",
    )
    with audio.open_audio_stream(output_config) as stream:
        assert stream is not None
        mock_output_stream.assert_called()


@patch("sounddevice.query_devices")
def test_device_filtering_by_capabilities(
    mock_query_devices: Mock,
) -> None:
    """Test that devices are properly filtered by input/output capabilities."""
    device_info = [
        {"index": 0, "name": "Input Only", "max_input_channels": 2, "max_output_channels": 0},
        {"index": 1, "name": "Output Only", "max_input_channels": 0, "max_output_channels": 2},
        {"index": 2, "name": "Both", "max_input_channels": 2, "max_output_channels": 2},
        {"index": 3, "name": "Neither", "max_input_channels": 0, "max_output_channels": 0},
    ]
    mock_query_devices.return_value = device_info

    # Test input device filtering
    _input_device_index, input_device_name = audio._input_device(
        input_device_name=None,
        input_device_index=0,
    )  # Input Only
    assert input_device_name == "Input Only"

    _mixed_input_index, mixed_input_name = audio._input_device(
        input_device_name=None,
        input_device_index=2,
    )  # Both
    assert mixed_input_name == "Both"

    # Test output device filtering
    _output_device_index, output_device_name = audio._output_device(
        input_device_name=None,
        input_device_index=1,
    )  # Output Only
    assert output_device_name == "Output Only"

    _mixed_output_index, mixed_output_name = audio._output_device(
        input_device_name=None,
        input_device_index=2,
    )  # Both
    assert mixed_output_name == "Both"


@pytest.mark.asyncio
async def test_audio_tee_error() -> None:
    """Test that the _AudioTee._run method handles an Exception."""
    mock_stream = Mock()
    mock_stream.read.side_effect = Exception("Test Error")
    mock_stop_event = Mock()
    mock_stop_event.is_set.return_value = False
    mock_logger = Mock()

    tee = audio._AudioTee(mock_stream, mock_stop_event, mock_logger)
    await tee._run()

    mock_logger.exception.assert_called_once_with("Error reading audio stream")
