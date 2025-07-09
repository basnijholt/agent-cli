"""General audio utilities for PyAudio device management and audio streaming."""

from __future__ import annotations

import asyncio
import functools
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING

import pyaudio
from rich.text import Text

from agent_cli import constants

from .utils import InteractiveStopEvent, console, print_device_index, print_with_style

if TYPE_CHECKING:
    import logging
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator

    from rich.live import Live

    from agent_cli import config


class _AudioTee:
    """A thread-safe class to tee a continuous PyAudio stream into multiple asyncio queues.

    This class reads from a single audio stream in a background task and forwards
    the audio chunks to any number of dynamically added consumer queues. It is designed
    to be started once and run for the lifetime of the stream.
    """

    def __init__(
        self,
        stream: pyaudio.Stream,
        stop_event: InteractiveStopEvent,
        logger: logging.Logger,
    ) -> None:
        """Initialize the AudioTee."""
        self.stream = stream
        self.stop_event = stop_event
        self.logger = logger
        self.queues: list[asyncio.Queue[bytes | None]] = []
        self._task: asyncio.Task | None = None
        self._stop_tee_event = asyncio.Event()
        self._lock = asyncio.Lock()  # For thread-safe modification of the queues list

    async def add_queue(self) -> asyncio.Queue[bytes | None]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        async with self._lock:
            self.queues.append(queue)
        self.logger.debug("Added a queue to the tee. Total queues: %d", len(self.queues))
        return queue

    async def remove_queue(self, queue: asyncio.Queue[bytes | None]) -> None:
        async with self._lock:
            if queue in self.queues:
                self.queues.remove(queue)
        # Signal the end of the stream for this specific queue consumer
        await queue.put(None)
        self.logger.debug("Removed a queue from the tee. Total queues: %d", len(self.queues))

    async def _run(self) -> None:
        """The main background task that reads from the stream and pushes to all queues."""
        self.logger.debug("Starting continuous audio reading task.")
        try:
            while not self.stop_event.is_set() and not self._stop_tee_event.is_set():
                chunk = await asyncio.to_thread(
                    self.stream.read,
                    num_frames=constants.PYAUDIO_CHUNK_SIZE,
                    exception_on_overflow=False,
                )
                # Lock the queue list while iterating to prevent modification during iteration
                async with self._lock:
                    for queue in self.queues:
                        await queue.put(chunk)
        except OSError:
            self.logger.exception("Error reading audio stream")
        finally:
            # Signal the end of the stream to all remaining consumers
            self.logger.debug("Stopping audio reading task and signaling all consumers.")
            async with self._lock:
                for queue in self.queues:
                    await queue.put(None)

    def start(self) -> None:
        """Start the background reading task."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background reading task gracefully."""
        if self._task and not self._task.done():
            self._stop_tee_event.set()
            await self._task
        self.logger.debug("Audio tee stopped successfully.")


@asynccontextmanager
async def tee_audio_stream(
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
) -> AsyncGenerator[_AudioTee, None]:
    """Context manager for an AudioTee."""
    tee = _AudioTee(stream, stop_event, logger)
    tee.start()
    try:
        yield tee
    finally:
        await tee.stop()


async def read_from_queue(
    queue: asyncio.Queue[bytes | None],
    chunk_handler: Callable[[bytes], None] | Callable[[bytes], Awaitable[None]],
    logger: logging.Logger,
) -> None:
    """Read audio chunks from a queue and call a handler."""
    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        if asyncio.iscoroutinefunction(chunk_handler):
            await chunk_handler(chunk)
        else:
            chunk_handler(chunk)
        logger.debug("Processed %d byte(s) of audio from queue", len(chunk))


@contextmanager
def pyaudio_context() -> Generator[pyaudio.PyAudio, None, None]:
    """Context manager for PyAudio lifecycle."""
    p = pyaudio.PyAudio()
    try:
        yield p
    finally:
        p.terminate()


@contextmanager
def open_pyaudio_stream(
    p: pyaudio.PyAudio,
    *args: object,
    **kwargs: object,
) -> Generator[pyaudio.Stream, None, None]:
    """Context manager for a PyAudio stream that ensures it's properly closed."""
    stream = p.open(*args, **kwargs)
    try:
        yield stream
    finally:
        stream.stop_stream()
        stream.close()


async def read_audio_stream(
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    chunk_handler: Callable[[bytes], None] | Callable[[bytes], Awaitable[None]],
    logger: logging.Logger,
    *,
    live: Live | None = None,
    quiet: bool = False,
    progress_message: str = "Processing audio",
    progress_style: str = "blue",
) -> None:
    """Core audio reading function - reads chunks and calls handler.

    This is the single source of truth for audio reading logic.
    All other audio functions should use this to avoid duplication.

    Args:
        stream: PyAudio stream
        stop_event: Event to stop reading
        chunk_handler: Function to handle each chunk (sync or async)
        logger: Logger instance
        live: Rich Live display for progress
        quiet: If True, suppress console output
        progress_message: Message to display
        progress_style: Rich style for progress

    """
    try:
        seconds_streamed = 0.0
        while not stop_event.is_set():
            chunk = await asyncio.to_thread(
                stream.read,
                num_frames=constants.PYAUDIO_CHUNK_SIZE,
                exception_on_overflow=False,
            )

            # Handle chunk (sync or async)
            if asyncio.iscoroutinefunction(chunk_handler):
                await chunk_handler(chunk)
            else:
                chunk_handler(chunk)

            logger.debug("Processed %d byte(s) of audio", len(chunk))

            # Update progress display
            seconds_streamed += len(chunk) / (
                constants.PYAUDIO_RATE * constants.PYAUDIO_CHANNELS * 2
            )
            if live and not quiet:
                if stop_event.ctrl_c_pressed:
                    msg = f"Ctrl+C pressed. Stopping {progress_message.lower()}..."
                    live.update(Text(msg, style="yellow"))
                else:
                    live.update(
                        Text(
                            f"{progress_message}... ({seconds_streamed:.1f}s)",
                            style=progress_style,
                        ),
                    )

    except OSError:
        logger.exception("Error reading audio")


def setup_input_stream(
    input_device_index: int | None,
) -> dict:
    """Get standard PyAudio input stream configuration.

    Args:
        input_device_index: Input device index

    Returns:
        Dictionary of stream parameters

    """
    return {
        "format": constants.PYAUDIO_FORMAT,
        "channels": constants.PYAUDIO_CHANNELS,
        "rate": constants.PYAUDIO_RATE,
        "input": True,
        "frames_per_buffer": constants.PYAUDIO_CHUNK_SIZE,
        "input_device_index": input_device_index,
    }


def setup_output_stream(
    output_device_index: int | None,
    *,
    sample_rate: int | None = None,
    sample_width: int | None = None,
    channels: int | None = None,
) -> dict:
    """Get standard PyAudio output stream configuration.

    Args:
        p: PyAudio instance
        output_device_index: Output device index
        sample_rate: Custom sample rate (defaults to config)
        sample_width: Custom sample width in bytes (defaults to config)
        channels: Custom channel count (defaults to config)

    Returns:
        Dictionary of stream parameters

    """
    return {
        "format": pyaudio.get_format_from_width(sample_width or 2),
        "channels": channels or constants.PYAUDIO_CHANNELS,
        "rate": sample_rate or constants.PYAUDIO_RATE,
        "output": True,
        "frames_per_buffer": constants.PYAUDIO_CHUNK_SIZE,
        "output_device_index": output_device_index,
    }


@functools.cache
def _get_all_devices(p: pyaudio.PyAudio) -> list[dict]:
    """Get information for all audio devices with caching.

    Args:
        p: PyAudio instance

    Returns:
        List of device info dictionaries with added 'index' field

    """
    devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        # Add the index to the info dict for convenience
        device_info = dict(info)
        device_info["index"] = i
        devices.append(device_info)
    return devices


def _get_device_by_index(p: pyaudio.PyAudio, input_device_index: int) -> dict:
    """Get device info by index from cached device list.

    Args:
        p: PyAudio instance
        input_device_index: Device index to look up

    Returns:
        Device info dictionary

    Raises:
        ValueError: If device index is not found

    """
    for device in _get_all_devices(p):
        if device["index"] == input_device_index:
            return device
    msg = f"Device index {input_device_index} not found"
    raise ValueError(msg)


def _list_input_devices(p: pyaudio.PyAudio) -> None:
    """Print a numbered list of available input devices."""
    console.print("[bold]Available input devices:[/bold]")
    for device in _get_all_devices(p):
        if device.get("maxInputChannels", 0) > 0:
            console.print(f"  [yellow]{device['index']}[/yellow]: {device['name']}")


def _list_output_devices(p: pyaudio.PyAudio) -> None:
    """Print a numbered list of available output devices."""
    console.print("[bold]Available output devices:[/bold]")
    for device in _get_all_devices(p):
        if device.get("maxOutputChannels", 0) > 0:
            console.print(f"  [yellow]{device['index']}[/yellow]: {device['name']}")


def list_all_devices(p: pyaudio.PyAudio) -> None:
    """Print a numbered list of all available audio devices with their capabilities."""
    _list_input_devices(p)
    console.print()
    _list_output_devices(p)


def _in_or_out_device(
    p: pyaudio.PyAudio,
    input_device_name: str | None,
    input_device_index: int | None,
    key: str,
    what: str,
) -> tuple[int | None, str | None]:
    """Find an input device by a prioritized, comma-separated list of keywords."""
    if input_device_name is None and input_device_index is None:
        return None, None

    if input_device_index is not None:
        info = _get_device_by_index(p, input_device_index)
        return input_device_index, info.get("name")
    assert input_device_name is not None
    search_terms = [term.strip().lower() for term in input_device_name.split(",") if term.strip()]

    if not search_terms:
        msg = "Device name string is empty or contains only whitespace."
        raise ValueError(msg)

    devices = []
    for device in _get_all_devices(p):
        device_info_name = device.get("name")
        if device_info_name and device.get(key, 0) > 0:
            devices.append((device["index"], device_info_name))

    for term in search_terms:
        for index, name in devices:
            if term in name.lower():
                return index, name

    msg = f"No {what} device found matching any of the keywords in {input_device_name!r}"
    raise ValueError(msg)


def _input_device(
    p: pyaudio.PyAudio,
    input_device_name: str | None,
    input_device_index: int | None,
) -> tuple[int | None, str | None]:
    """Find an input device by a prioritized, comma-separated list of keywords."""
    return _in_or_out_device(p, input_device_name, input_device_index, "maxInputChannels", "input")


def _output_device(
    p: pyaudio.PyAudio,
    input_device_name: str | None,
    input_device_index: int | None,
) -> tuple[int | None, str | None]:
    """Find an output device by a prioritized, comma-separated list of keywords."""
    return _in_or_out_device(
        p,
        input_device_name,
        input_device_index,
        "maxOutputChannels",
        "output",
    )


def setup_devices(
    p: pyaudio.PyAudio,
    general_config: config.General,
    audio_in_cfg: config.AudioInput | None,
    audio_out_cfg: config.AudioOutput | None,
) -> tuple[int | None, str | None, int | None] | None:
    """Handle device listing and setup."""
    if general_config.list_devices:
        list_all_devices(p)
        return None

    # Setup input device
    input_device_index, input_device_name = _input_device(
        p,
        audio_in_cfg.input_device_name if audio_in_cfg else None,
        audio_in_cfg.input_device_index if audio_in_cfg else None,
    )
    if not general_config.quiet:
        print_device_index(input_device_index, input_device_name)

    # Setup output device for TTS if enabled
    tts_output_device_index = audio_out_cfg.output_device_index if audio_out_cfg else None
    if (
        audio_out_cfg
        and audio_out_cfg.enable_tts
        and (audio_out_cfg.output_device_name or audio_out_cfg.output_device_index)
    ):
        tts_output_device_index, tts_output_device_name = _output_device(
            p,
            audio_out_cfg.output_device_name,
            audio_out_cfg.output_device_index,
        )
        if tts_output_device_index is not None and not general_config.quiet:
            msg = f"🔊 TTS output device [bold yellow]{tts_output_device_index}[/bold yellow] ([italic]{tts_output_device_name}[/italic])"
            print_with_style(msg)

    return input_device_index, input_device_name, tts_output_device_index
