"""Unit tests for audio configuration helpers."""

from agent_cli.core import audio


def test_setup_input_stream_uses_custom_sample_rate():
    stream_kwargs = audio.setup_input_stream(input_device_index=None, sample_rate=32000)

    assert stream_kwargs["rate"] == 32000
