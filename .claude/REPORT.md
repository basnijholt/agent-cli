# ASR Model Persistence Fix Report

## Summary

Fixed the `FasterWhisperBackend` to persist the Whisper model across transcription calls instead of reloading it fresh each time.

## Changes Made

**File**: `agent_cli/server/whisper/backends/faster_whisper.py`

1. Added `_SubprocessState` dataclass (lines 30-35) to hold subprocess-local state:
   - `model`: The loaded WhisperModel instance
   - `device`: The device string (cuda/cpu)

2. Added module-level `_state = _SubprocessState()` instance (line 38)

3. Modified `_load_model_in_subprocess` to store the model in `_state`:
   - After loading, sets `_state.model` and `_state.device`
   - Returns `_state.device` instead of computing it inline

4. Simplified `_transcribe_in_subprocess`:
   - Removed model config parameters (model_name, device, compute_type, etc.)
   - Now only takes `audio_bytes` and `kwargs`
   - Reuses `_state.model` instead of creating a new WhisperModel
   - Added runtime check if model is not loaded

5. Updated `transcribe()` method to pass only the necessary parameters to the subprocess function

## Measured Performance

### tiny model (CPU, 1 second audio)

```
Model load time: 2.198s

5 transcription calls:
  Call 1: 0.359s
  Call 2: 0.311s
  Call 3: 0.344s
  Call 4: 0.339s
  Call 5: 0.336s

OLD (reload each call): ~2.54s per transcription
NEW (model persisted):  ~0.34s per transcription
Speedup: 7.5x faster
Time saved per call: 2.2s
```

### large-v3 model (CPU, 1 second audio)

```
Model load time: 7.144s

5 transcription calls:
  Call 1: 7.193s
  Call 2: 6.340s
  Call 3: 6.513s
  Call 4: 6.419s
  Call 5: 6.667s

OLD (reload each call): ~13.77s per transcription
NEW (model persisted):  ~6.63s per transcription
Speedup: 2.1x faster
Time saved per call: 7.1s
```

## Memory Usage Comparison

Tested with tiny model on CPU over 10 transcription calls:

### OLD behavior (reload model each call)
```
Subprocess memory after 1st call: 635.3 MB

10 calls:
  Call 1: 695.5 MB
  Call 2: 698.5 MB
  Call 3: 737.2 MB
  Call 4: 738.7 MB
  ...
  Call 10: 798.8 MB

Memory growth: +103.3 MB (695 → 799 MB)
```

### NEW behavior (persist model)
```
Subprocess memory after load: 625.2 MB

10 calls:
  Call 1: 664.1 MB
  Call 2: 664.3 MB
  ...
  Call 10: 664.3 MB

Memory growth: +0.1 MB (stable at ~664 MB)
```

**The old code leaked ~10 MB per call** because Python's garbage collector doesn't fully reclaim the old model before the new one loads.

## Design Notes

The pattern follows the existing Kokoro TTS backend implementation exactly:
- `_SubprocessState` dataclass for state container
- Module-level `_state` instance
- State persists because ProcessPoolExecutor reuses the same worker process
- State is subprocess-local (not shared with main process via IPC)

## Concerns

None. The implementation:
- Passes all 913 existing tests
- Passes all pre-commit checks (ruff, mypy, etc.)
- Follows established patterns in the codebase
- Maintains subprocess isolation for memory management
- **Fixes memory leak** in addition to improving performance
