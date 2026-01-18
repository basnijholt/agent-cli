"""Tests for server streaming primitives."""

from __future__ import annotations

from multiprocessing import Queue

import pytest

from agent_cli.server.streaming import AsyncQueueReader, QueueWriter, StreamChunk


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_data_chunk(self) -> None:
        """Test creating a data chunk."""
        chunk = StreamChunk("data", b"audio bytes")
        assert chunk.chunk_type == "data"
        assert chunk.payload == b"audio bytes"
        assert chunk.metadata is None

    def test_error_chunk(self) -> None:
        """Test creating an error chunk."""
        chunk = StreamChunk("error", "something went wrong")
        assert chunk.chunk_type == "error"
        assert chunk.payload == "something went wrong"

    def test_done_chunk_with_metadata(self) -> None:
        """Test creating a done chunk with metadata."""
        meta = {"duration": 1.5, "samples": 24000}
        chunk = StreamChunk("done", metadata=meta)
        assert chunk.chunk_type == "done"
        assert chunk.payload is None
        assert chunk.metadata == meta


class TestQueueWriter:
    """Tests for QueueWriter helper."""

    def test_send_data(self) -> None:
        """Test sending data chunk."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_data(b"test data")

        chunk = queue.get(timeout=1)
        assert chunk.chunk_type == "data"
        assert chunk.payload == b"test data"
        assert chunk.metadata is None

    def test_send_data_with_metadata(self) -> None:
        """Test sending data chunk with metadata."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_data(b"test", {"index": 0})

        chunk = queue.get(timeout=1)
        assert chunk.metadata == {"index": 0}

    def test_send_error_from_string(self) -> None:
        """Test sending error from string."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_error("error message")

        chunk = queue.get(timeout=1)
        assert chunk.chunk_type == "error"
        assert chunk.payload == "error message"

    def test_send_error_from_exception(self) -> None:
        """Test sending error from exception."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_error(ValueError("bad value"))

        chunk = queue.get(timeout=1)
        assert chunk.chunk_type == "error"
        assert chunk.payload == "bad value"

    def test_send_done(self) -> None:
        """Test sending done sentinel."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_done()

        chunk = queue.get(timeout=1)
        assert chunk.chunk_type == "done"
        assert chunk.metadata is None

    def test_send_done_with_metadata(self) -> None:
        """Test sending done with final metadata."""
        queue: Queue[StreamChunk] = Queue()
        writer = QueueWriter(queue)

        writer.send_done({"total_bytes": 1000})

        chunk = queue.get(timeout=1)
        assert chunk.chunk_type == "done"
        assert chunk.metadata == {"total_bytes": 1000}


class TestAsyncQueueReader:
    """Tests for AsyncQueueReader."""

    @pytest.mark.asyncio
    async def test_reads_chunks(self) -> None:
        """Test reading chunks from queue."""
        queue: Queue[StreamChunk] = Queue()
        queue.put(StreamChunk("data", b"chunk1"))
        queue.put(StreamChunk("done"))

        reader = AsyncQueueReader(queue)
        chunks = []

        async for chunk in reader:
            chunks.append(chunk)
            if chunk.chunk_type == "done":
                break

        assert len(chunks) == 2
        assert chunks[0].chunk_type == "data"
        assert chunks[1].chunk_type == "done"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Timeout test unreliable - queue.get blocks in executor")
    async def test_timeout_raises(self) -> None:
        """Test that timeout raises TimeoutError."""
        queue: Queue[StreamChunk] = Queue()  # Empty queue
        reader = AsyncQueueReader(queue, timeout=0.05)

        with pytest.raises(TimeoutError, match="Queue read timeout"):
            await reader.__anext__()

    @pytest.mark.asyncio
    async def test_aiter_returns_self(self) -> None:
        """Test that __aiter__ returns self."""
        queue: Queue[StreamChunk] = Queue()
        reader = AsyncQueueReader(queue)
        assert reader.__aiter__() is reader
