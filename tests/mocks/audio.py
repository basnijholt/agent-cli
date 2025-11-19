"""Mock SoundDevice for testing audio functionality without real hardware."""

from __future__ import annotations

from typing import Any, Self

import numpy as np


class MockSoundDeviceStream:
    """Mock sounddevice stream for testing."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize mock audio stream."""
        self.args = args
        self.kwargs = kwargs
        self.is_input = kwargs.get("input", False) or isinstance(self, MockInputStream)
        self.is_output = kwargs.get("output", False) or isinstance(self, MockOutputStream)
        self.written_data: list[bytes] = []
        self.active = False
        self._closed = False

    def start(self) -> None:
        """Start the mock stream."""
        self.active = True

    def stop(self) -> None:
        """Stop the mock stream."""
        self.active = False

    def close(self) -> None:
        """Close the mock stream."""
        self._closed = True
        self.active = False

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        """Simulate reading from audio input device.

        Returns:
            tuple: (data, overflow)

        """
        dtype = self.kwargs.get("dtype", "int16")
        channels = self.kwargs.get("channels", 1)

        shape = (frames, channels) if channels > 1 else (frames,)

        if dtype == "int16":
            data = np.full(shape, 1, dtype=np.int16)
        else:
            data = np.zeros(shape, dtype=np.float32)

        return data, False

    def write(self, data: np.ndarray) -> None:
        """Simulate writing to audio output device."""
        # data is numpy array
        self.written_data.append(data.tobytes())

    def get_written_data(self) -> bytes:
        """Get all written data concatenated."""
        return b"".join(self.written_data)

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()


class MockInputStream(MockSoundDeviceStream):
    """Mock input stream."""


class MockOutputStream(MockSoundDeviceStream):
    """Mock output stream."""
