---
icon: lucide/mic
---

# whisper

> [!WARNING]
> `agent-cli server whisper` is deprecated and will be removed in a future release.
> Use [`agent-cli server asr`](asr.md) instead.

The command was renamed because it serves more than Whisper models (faster-whisper, MLX, transformers, and NeMo/Parakeet backends).
The `whisper` alias accepts the same options as `asr` and prints a deprecation warning when used.

```bash
# Before
agent-cli server whisper --model large-v3

# After
agent-cli server asr --model large-v3
```

The `whisper` background service keeps its name; `agent-cli daemon install whisper` now installs it with `agent-cli server asr`.
Services installed by older versions keep running `server whisper` (and log the deprecation warning) until you reinstall them.
Pass the same extra arguments you used originally, for example:

```bash
agent-cli daemon install whisper -- --backend nemo --ttl 0
```
