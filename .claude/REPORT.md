# Report: WebSocket Streaming Transcription Support

## Summary

Updated the WebSocket endpoint `/v1/audio/transcriptions/stream` to support real-time partial transcriptions when the backend supports streaming, with graceful fallback to buffered mode when streaming is not available.

## What Was Implemented

### 1. Backend Protocol Updates (`agent_cli/server/whisper/backends/base.py`)

Added streaming support to the `WhisperBackend` protocol:

- **`PartialTranscriptionResult`** dataclass: Holds partial transcription results with fields:
  - `text`: The transcribed text so far
  - `is_final`: Whether this is the final result
  - `language`: Detected language (optional)
  - `segment_start` / `segment_end`: Timing information (optional)

- **`supports_streaming`** property: Indicates whether the backend supports streaming transcription (default: `False`)

- **`transcribe_stream`** method: Async generator that yields `PartialTranscriptionResult` as audio is processed

### 2. Backend Implementations

Updated both backends to implement the new protocol:

- **`FasterWhisperBackend`** (`backends/faster_whisper.py`): Added `supports_streaming = False` and stub `transcribe_stream` method
- **`MLXWhisperBackend`** (`backends/mlx.py`): Added `supports_streaming = False` and stub `transcribe_stream` method

### 3. Model Manager Updates (`agent_cli/server/whisper/model_manager.py`)

Added streaming support to `WhisperModelManager`:

- **`supports_streaming`** property: Delegates to the underlying backend
- **`transcribe_stream`** method: Wraps backend streaming with request tracking and stats

### 4. WebSocket Endpoint Updates (`agent_cli/server/whisper/api.py`)

Refactored the WebSocket endpoint with two modes:

- **Streaming mode** (when `manager.supports_streaming` is `True`):
  - Uses an async queue to receive audio chunks
  - Passes chunks to `manager.transcribe_stream`
  - Sends partial results as they become available
  - Message format: `{"type": "partial", "text": "...", "is_final": false}`

- **Buffered mode** (fallback when streaming not supported):
  - Collects all audio chunks until EOS marker
  - Transcribes once at the end
  - Sends final result: `{"type": "final", "text": "...", "is_final": true, "segments": [...]}`

## How Partial Transcriptions Are Triggered

When streaming is supported:

1. Client connects to WebSocket and sends audio chunks
2. Audio chunks are pushed to an async queue
3. An async generator consumes from the queue and feeds to `transcribe_stream`
4. Backend yields `PartialTranscriptionResult` objects as segments complete
5. Each result is immediately sent to the client via WebSocket
6. When client sends `EOS` marker, the queue signals end of stream
7. Backend yields final result with `is_final=True`

## Fallback Behavior

When streaming is NOT supported (current state for both backends):

1. WebSocket endpoint checks `manager.supports_streaming` before receiving audio
2. Since it's `False`, uses `_handle_buffered_transcription`
3. Collects all audio into a WAV buffer
4. On EOS, transcribes entire buffer at once
5. Returns single final result (same as before)

## Message Format

```json
// Partial result (streaming mode only)
{"type": "partial", "text": "Hello", "is_final": false, "language": "en", "segment_start": 0.0, "segment_end": 1.5}

// Final result (both modes)
{"type": "final", "text": "Hello world", "is_final": true, "language": "en", "duration": 2.5, "segments": [...]}

// Error
{"type": "error", "message": "..."}
```

## Testing

- All 909 tests pass
- Pre-commit checks pass (ruff, mypy, etc.)
- Existing WebSocket tests continue to work with buffered mode

## Follow-up Work Needed

1. **Implement Streaming Backend** (Task 2): The current backends (`faster-whisper`, `mlx`) don't support true streaming. A future task should implement a streaming backend (e.g., using whisper.cpp with streaming support or a custom VAD-based chunked approach).

2. **VAD Integration**: For practical partial transcription without native streaming support, could implement VAD-based chunking that transcribes after detecting speech pauses.

3. **Client Documentation**: Document the WebSocket protocol changes for clients that want to use streaming mode.

## Files Changed

- `agent_cli/server/whisper/backends/base.py` - Added streaming types and protocol methods
- `agent_cli/server/whisper/backends/__init__.py` - Export new types
- `agent_cli/server/whisper/backends/faster_whisper.py` - Added streaming stubs
- `agent_cli/server/whisper/backends/mlx.py` - Added streaming stubs
- `agent_cli/server/whisper/model_manager.py` - Added streaming methods
- `agent_cli/server/whisper/api.py` - Refactored WebSocket with streaming/buffered modes
