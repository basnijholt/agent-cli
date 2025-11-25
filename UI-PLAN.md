# UI Development Plan: Agent CLI Desktop

> **Status**: Active / Phase 1 Complete
> **Last Updated**: 2025-11-24

## 1. The Vision
**"GUI as a View, CLI as the Model"**

The goal is to elevate `agent-cli` from a terminal utility to a persistent desktop assistant.
- **The Brain (Python)**: Handles all logic, memory, RAG, LLM orchestration, and hardware I/O (Wyoming/Whisper).
- **The Face (Electron/React)**: A modern, interactive layer for chat, voice visualization, and context inspection.

The UI does **not** reimplement AI logic. It is a "dumb" client that talks to the local `agent-cli` REST APIs.

## 2. Architecture

```mermaid
graph TD
    User[User] --> UI[Electron / React App]

    subgraph "Frontend (UI/)"
        UI -->|POST Audio| TranscribeAPI
        UI -->|POST Chat| MemoryAPI
    end

    subgraph "Backend (agent_cli/)"
        TranscribeAPI[Server (Port 61337)]
        MemoryAPI[Memory Proxy (Port 8100)]
        RAG[RAG Proxy (Port 8000)]

        TranscribeAPI --> Whisper[Wyoming Whisper]
        MemoryAPI --> Chroma[ChromaDB Memory]
        MemoryAPI --> LLM[Ollama / OpenAI]

        MemoryAPI -.-> RAG
    end
```

## 3. Technical Stack

- **Runtime**: Bun (Package Manager & Bundling helpers), Node.js (Electron runtime).
- **Build**: Vite (React HMR & Build pipeline).
- **Framework**: React 18 + TypeScript.
- **UI Library**: `assistant-ui` (v0.11+ using Primitives), Tailwind CSS.
- **Desktop Wrapper**: Electron + `electron-builder`.
- **Communication**: REST (Client-side fetching directly to localhost ports).

## 4. Roadmap & Status

### Phase 1: The Foundation (✅ Completed)
*   **Goal**: Establish a working chat window connected to the Python backend.
*   **Accomplished**:
    *   [x] Scaffolded `UI/` directory with Vite + React + TypeScript using Bun.
    *   [x] Configured `electron` main process and IPC preload scripts.
    *   [x] Enabled CORS in `agent_cli/api.py` to allow browser requests.
    *   [x] Implemented basic Chat UI using `assistant-ui` **Primitives** (`ThreadPrimitive`, `ComposerPrimitive`) to avoid versioning issues.
    *   [x] Connected Chat UI to `http://localhost:8100/v1/chat/completions` (Memory Proxy).
    *   [x] Added `vitest` setup with `jsdom` and `ResizeObserver` polyfills.

### Phase 2: Voice Integration (🚧 Next Up)
*   **Goal**: Replicate `agent-cli transcribe` in the browser.
*   **Strategy**:
    1.  Implement a custom "Record" button in the `Composer` component.
    2.  Use Browser `MediaRecorder` API to capture audio.
    3.  POST `Blob` to `http://localhost:61337/transcribe` (The `agent-cli server`).
    4.  Inject returned text into the Composer input.

### Phase 3: Context & RAG Visualization (📅 Planned)
*   **Goal**: Show *why* the agent knows what it knows.
*   **Strategy**:
    *   Parse RAG citations from the backend (e.g., `[Source: file.md]`).
    *   Render clickable UI badges for sources.
    *   Visualize Memory updates (e.g., "Memory updated: User lives in Amsterdam").

### Phase 4: System Integration (📅 Planned)
*   **Goal**: Native desktop feel.
*   **Strategy**:
    *   Global Hotkey (`Cmd+Shift+K`) to toggle window visibility.
    *   "Always on Top" / Floating mode.
    *   System Tray icon.

## 5. How to Run

### Prerequisites
1.  **Python Backend**:
    ```bash
    # Terminal 1
    agent-cli start-services
    # Terminal 2
    agent-cli memory-proxy
    ```

### Development
```bash
cd UI
bun install
bun run dev:electron  # Runs Vite + Electron concurrently
```

### Testing
```bash
cd UI
bun run test
```

## 6. Context for the Next Agent
If you are reading this, you are likely continuing development.
- **Current State**: The app launches, renders a chat window, and can send text messages to the backend if `memory-proxy` is running.
- **Codebase Structure**:
    - `UI/src/App.tsx`: Main entry point. Contains the `Thread` implementation using primitives.
    - `UI/electron/`: Main process code.
    - `agent_cli/api.py`: The FastAPI backend (modified for CORS).
- **Immediate Task**: Implement **Phase 2 (Voice Integration)**. Look at `agent_cli/agents/server.py` and `agent_cli/api.py` to understand the `/transcribe` endpoint expectation (multipart form data).
