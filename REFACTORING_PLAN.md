# Agent-CLI Refactoring Plan

## 1. Goal

The primary goal of this refactoring is to improve the overall organization of the `agent-cli` package. This involves restructuring the project to better separate concerns, reduce cross-dependencies between modules, and make the codebase more intuitive, maintainable, and extensible.

## 2. Proposed File Structure

The new architecture will introduce `core` and `services` packages to logically group related functionality.

```
agent_cli/
├── __init__.py
├── cli.py
├── constants.py
├── py.typed
├── agents/
│   ├── __init__.py
│   ├── _cli_options.py
│   ├── _tts_common.py
│   ├── _voice_agent_common.py
│   ├── assistant.py
│   ├── autocorrect.py
│   ├── chat.py
│   ├── speak.py
│   ├── transcribe.py
│   └── voice_edit.py
├── config.py          # New unified config module
├── core/              # New package for core logic
│   ├── __init__.py
│   ├── audio.py       # For audio device I/O
│   ├── process.py     # For process management
│   └── utils.py       # For generic utilities
└── services/          # New package for external service integrations
    ├── __init__.py
    ├── base.py        # Abstract base classes for services
    ├── factory.py     # Factory to get the correct service
    ├── local.py       # Implementations for local services (Wyoming/Ollama)
    └── openai.py      # Implementations for OpenAI services
```

## 3. Detailed Migration Plan

### Step 1: Consolidate Configuration

-   **Action:** Create a new `agent_cli/config.py` file.
-   **Source Logic:** Merge the contents of `agent_cli/config_loader.py` and `agent_cli/agents/config.py`.
-   **Content:**
    -   **Loading Logic:** `load_config()`, `_replace_dashed_keys()` from `config_loader.py`.
    -   **Pydantic Models:** All configuration models (`ProviderSelection`, `Ollama`, `OpenAILLM`, `AudioInput`, `WyomingASR`, `OpenAIASR`, `AudioOutput`, `WyomingTTS`, `OpenAITTS`, `WakeWord`, `General`, `History`).
-   **Cleanup:** Delete `agent_cli/config_loader.py` and `agent_cli/agents/config.py`.

### Step 2: Create `core` Package

-   **Action:** Create a new directory `agent_cli/core/`.
-   **`agent_cli/core/audio.py`**:
    -   **Action:** Move `agent_cli/audio.py` to `agent_cli/core/audio.py`.
    -   **Content:** All PyAudio device management and streaming logic.
-   **`agent_cli/core/process.py`**:
    -   **Action:** Move `agent_cli/process_manager.py` to `agent_cli/core/process.py`.
    -   **Content:** All PID file and process management functions.
-   **`agent_cli/core/utils.py`**:
    -   **Action:** Create `agent_cli/core/utils.py` and move generic helpers from `agent_cli/utils.py`.
    -   **Content:** `console`, `InteractiveStopEvent`, `signal_handling_context`, `live_timer`, `print_*_panel`, `get_clipboard_text`.

### Step 3: Create `services` Package

-   **Action:** Create a new directory `agent_cli/services/`.
-   **`agent_cli/services/base.py`** (New File):
    -   **Content:** Define Abstract Base Classes (ABCs) for `ASRService`, `LLMService`, and `TTSService`.
-   **`agent_cli/services/local.py`** (New File):
    -   **Content:** Implementations for all local services.
        -   **Wyoming ASR:** Logic from `asr.py`.
        -   **Wyoming TTS:** Logic from `tts.py`.
        -   **Wyoming Wake Word:** Logic from `wake_word.py`.
        -   **Ollama LLM:** Logic from `llm.py`.
        -   **Wyoming Utils:** `wyoming_client_context` from `wyoming_utils.py`.
-   **`agent_cli/services/openai.py`** (New File):
    -   **Content:** Implementations for all OpenAI services.
        -   **OpenAI ASR:** Logic from `services.py` and `asr.py`.
        -   **OpenAI TTS:** Logic from `services.py` and `tts.py`.
        -   **OpenAI LLM:** Logic from `llm.py`.
-   **`agent_cli/services/factory.py`** (New File):
    -   **Content:** Factory functions (`get_asr_service`, `get_llm_service`, `get_tts_service`) that return the correct service implementation based on the user's configuration.

### Step 4: Refactor and Cleanup

-   **Action:** Update all imports across the project to reflect the new structure.
-   **Action:** Delete the old, now-empty files: `asr.py`, `llm.py`, `tts.py`, `wake_word.py`, `services.py`, `process_manager.py`, `config_loader.py`, `wyoming_utils.py`, and `agents/config.py`.
-   **Action:** Refactor `agent_cli/utils.py` to remove the functions that were moved to `core/utils.py`.
