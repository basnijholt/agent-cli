# VAD-based Streaming for WebSocket Transcription Endpoint

## Summary

Added Voice Activity Detection (VAD) to the WebSocket endpoint `/v1/audio/transcriptions/stream` so remote clients receive partial transcriptions as speech segments complete, rather than waiting for the entire audio stream.

## Implementation Details

### Changes Made

**File: `agent_cli/server/whisper/api.py`**

1. **VAD Import and Availability Check**
   - Added conditional import of `VoiceActivityDetector` from `agent_cli/core/vad`
   - Created `_VAD_AVAILABLE` flag to gracefully handle when the `vad` extra is not installed
   - Added `_create_vad()` helper function that raises a clear error if VAD is requested but not available

2. **New Query Parameters**
   - `use_vad: bool = True` - Enable/disable VAD (defaults to enabled)
   - `vad_threshold: float = 0.3` - Speech detection threshold (0.0-1.0)
   - `vad_silence_ms: int = 1000` - Silence duration (ms) to end speech segment
   - `vad_min_speech_ms: int = 250` - Minimum speech duration (ms) to trigger transcription

3. **New Handler Functions**
   - `_stream_with_vad()` - Handles VAD-enabled streaming with partial results
   - `_stream_buffered()` - Preserves the original buffered behavior (no VAD)
   - `_transcribe_segment()` - Helper to wrap raw PCM in WAV format for transcription

### VAD Parameters Exposed

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `use_vad` | bool | `true` | - | Enable VAD for streaming partial results |
| `vad_threshold` | float | `0.3` | 0.0-1.0 | Speech detection threshold |
| `vad_silence_ms` | int | `1000` | 100-5000 | Silence duration (ms) to end segment |
| `vad_min_speech_ms` | int | `250` | 50-2000 | Min speech duration (ms) to trigger transcription |

### Message Protocol

The protocol remains backward compatible:

```json
// Partial transcriptions (VAD mode only)
{"type": "partial", "text": "first utterance", "is_final": false, "language": "en"}
{"type": "partial", "text": "second utterance", "is_final": false, "language": "en"}

// Final combined result
{"type": "final", "text": "first utterance second utterance", "is_final": true, "language": "en"}

// Error
{"type": "error", "message": "..."}
```

### Backward Compatibility

- **VAD not installed**: If a client requests `use_vad=true` but the `vad` extra is not installed, an error message is returned explaining how to install it
- **VAD disabled**: Clients can use `use_vad=false` to get the original buffered behavior where all audio is collected before transcription
- **Default behavior change**: VAD is now enabled by default, which provides a better experience for streaming clients

## Test Updates

Updated existing WebSocket tests to use `use_vad=false` since they send silence audio (`\x00\x00` bytes) that VAD correctly identifies as non-speech.

## Edge Cases & Concerns

1. **Empty audio**: If no speech segments are detected, the final message will have an empty `text` field
2. **VAD dependency**: The `vad` extra (silero-vad, torch, numpy) must be installed for VAD to work
3. **Model loading**: Each segment transcription requires the Whisper model, which is managed by the existing TTL-based caching
4. **Segment boundaries**: Speech segments may not align with natural sentence boundaries; the LLM cleanup feature (if enabled) can help post-process
