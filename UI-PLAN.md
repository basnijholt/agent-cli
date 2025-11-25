# UI Development Plan: Agent CLI Desktop

> **Status**: Active / Phase 3.5 Completed
> **Last Updated**: 2025-11-25
> **Next Step**: Phase 4 - Voice Integration

## 1. The Vision

**"GUI as a View, CLI as the Model"**

The goal is to elevate `agent-cli` from a terminal utility to a persistent desktop assistant.

- **The Brain (Python)**: Handles all logic, memory, RAG, LLM orchestration, and hardware I/O (Wyoming/Whisper).
- **The Face (React Web App)**: A modern, interactive layer for chat, voice visualization, and context inspection.

The UI does **not** reimplement AI logic. It is a "dumb" client that talks to the local `agent-cli` REST APIs.

### Key Principle: Native Assistant-UI First

**IMPORTANT**: Before building any custom UI component, check if `assistant-ui` provides native support:

- **Thread List (Multiple Chats)** → Use `ThreadListPrimitive`, NOT custom Sidebar
- **Model Configuration** → Use `ModelContext`, NOT custom state management
- **Message Display** → Use `MessagePrimitive`, NOT custom components
- **Conversation Switching** → Use Runtime Adapter interfaces, NOT manual state

The correct approach is to implement **Runtime Adapters** that connect assistant-ui's native interfaces to our backend API.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Browser (Web App)                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │         AssistantRuntimeProvider                            ││
│  │              (useAgentCLIRuntime)                           ││
│  │  ┌─────────────────┐  ┌─────────────────────────────────┐  ││
│  │  │ ThreadListPrim. │  │  ThreadPrimitive                │  ││
│  │  │ (native sidebar)│  │  ┌─────────────────────────────┐│  ││
│  │  │                 │  │  │ MessagePrimitive (messages) ││  ││
│  │  │ • Chat 1        │  │  └─────────────────────────────┘│  ││
│  │  │ • Chat 2        │  │  ┌─────────────────────────────┐│  ││
│  │  │ [+ New Thread]  │  │  │ ComposerPrimitive (input)   ││  ││
│  │  └─────────────────┘  │  └─────────────────────────────┘│  ││
│  │                       └─────────────────────────────────┘  ││
│  │  ModelContext (model/settings passed to API calls)         ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────┬──────────────────────────────┘
                                   │ HTTP (Port 8100)
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Memory Proxy API                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ POST /v1/chat/completions     (chat with memory)          │  │
│  │ GET  /v1/conversations        (list threads) ✅ exists    │  │
│  │ GET  /v1/conversations/{id}   (get history)  ✅ exists    │  │
│  │ POST /transcribe              (voice - future)            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Memory Store │ ChromaDB │ Ollama/OpenAI/Gemini │ Wyoming │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Technical Stack

- **Runtime**: Bun (Package Manager), Vite (Build).
- **Framework**: React 18 + TypeScript.
- **UI Library**: `@assistant-ui/react` (using **Runtime Adapters** + **Primitives**), Tailwind CSS.
- **Platform**: Web-first (browser). Electron/iOS wrappers deferred.
- **Communication**: REST to localhost:8100.

### Assistant-UI Integration Strategy

```typescript
// CORRECT: Use Runtime Adapter that implements thread list interface
const runtime = useAgentCLIRuntime({
  // Thread list operations → backend API
  listThreads: () => fetch('/v1/conversations'),
  loadThread: (id) => fetch(`/v1/conversations/${id}`),
  createThread: () => { /* create new conversation */ },

  // Chat operations → backend API
  chat: (messages, threadId, modelConfig) => fetch('/v1/chat/completions', {
    body: { messages, memory_id: threadId, model: modelConfig.model }
  }),
});

// INCORRECT: Manual state management on top of useChat
// const [conversations, setConversations] = useState([]);
// const [currentId, setCurrentId] = useState("default");
```

## 4. Roadmap & Status

### Phase 1: Foundation (✅ Completed)

- [x] Scaffolded `UI/` with Vite + React + TypeScript + Bun
- [x] Basic chat using `ThreadPrimitive`, `ComposerPrimitive`, `MessagePrimitive`
- [x] Connected to `http://localhost:8100/v1/chat/completions`
- [x] Added vitest setup

### Phase 1.5: Backend API (✅ Completed)

- [x] `GET /v1/conversations` - List conversation IDs
- [x] `GET /v1/conversations/{id}` - Get conversation history
- [x] CORS enabled

### Phase 2: Native Thread List Integration (✅ Completed)

**Goal**: Multi-session chat using assistant-ui's native `ThreadListPrimitive`.

**Completed**:

- [x] Created `useAgentCLIRuntime` hook (`UI/src/runtime/useAgentCLIRuntime.ts`) that implements:
  - `load` callback to fetch conversation history from backend
  - `create` callback to generate new thread IDs
  - `stream` callback to send messages via SSE streaming
  - OpenAI ↔ LangChain message format conversion

- [x] Refactored `App.tsx` to use:
  - `ThreadListPrimitive` for sidebar via `ThreadList` component
  - `ThreadPrimitive` for chat view via `Thread` component
  - Single `AssistantRuntimeProvider` with our runtime

- [x] Replaced custom components with primitives:
  - Deleted `Sidebar.tsx` → Replaced with `ThreadList.tsx` using `ThreadListPrimitive`
  - Deleted `ChatArea.tsx` → Logic moved to runtime
  - Deleted `SettingsModal.tsx` → Deferred to Phase 3
  - Kept `Thread.tsx` wrapping primitives

**Key files created/modified**:
- `UI/src/runtime/useAgentCLIRuntime.ts` - NEW: Runtime adapter hook
- `UI/src/components/ThreadList.tsx` - NEW: Native thread list using primitives
- `UI/src/components/Thread.tsx` - SIMPLIFIED: Removed markdown dep
- `UI/src/App.tsx` - REFACTORED: Uses runtime provider

**Reference**: Based on `assistant-ui/examples/with-langgraph/` pattern.

### Phase 3: Model & Settings (✅ Completed)

**Goal**: Switch models and configure RAG parameters.

**Completed**:

- [x] Created `SettingsModal.tsx` component with:
  - Model selector dropdown fetched dynamically from `/v1/models` API
  - RAG `memory_top_k` parameter input (1-20 range)
  - Current configuration display
  - Cancel/Save buttons with proper state management

- [x] Updated `App.tsx` to:
  - Lift configuration state to App level
  - Fetch models on startup and auto-select first available model
  - Pass dynamic config to `useAgentCLIRuntime`
  - Manage settings modal open/close state

- [x] Updated `ThreadList.tsx` to add Settings button in sidebar footer

- [x] **Major refactor**: Replaced `useLangGraphRuntime` with `useExternalStoreRuntime`
  - **Root cause**: `useLangGraphRuntime` requires AssistantCloud. Without it, falls back to `InMemoryThreadListAdapter` which always returns `externalId: undefined`, causing "Thread not found" errors.
  - **Solution**: Use `useExternalStoreRuntime` for full control over message/thread state
  - Implemented `onNew`, `onSwitchToThread`, `onSwitchToNewThread` callbacks
  - Custom SSE streaming parser for chat responses
  - Support for `reasoning_content` (thinking models like qwen3-thinking)

- [x] **Added Playwright E2E tests** (`UI/e2e/chat.spec.ts`):
  - UI element loading test
  - Settings modal with model fetching test
  - Chat message sending and streaming response test
  - Thinking model `reasoning_content` handling test
  - No-model-selected error state test
  - All 5 tests passing

**Key files created/modified**:
- `UI/src/components/SettingsModal.tsx` - NEW: Settings modal component (fetches models from API)
- `UI/src/App.tsx` - MODIFIED: Lifted config state, added modal, fetches models on startup
- `UI/src/components/ThreadList.tsx` - MODIFIED: Added Settings button
- `UI/src/runtime/useAgentCLIRuntime.ts` - REWRITTEN: Uses `useExternalStoreRuntime` instead of `useLangGraphRuntime`
- `UI/e2e/chat.spec.ts` - NEW: Playwright E2E tests
- `UI/playwright.config.ts` - NEW: Playwright configuration

**Note**: Settings persist in React state (session-only). LocalStorage persistence can be added later if needed.

### Phase 3.5: Conversation Persistence (✅ Completed)

**Goal**: Persist conversations across page refresh and populate thread list from backend.

**Completed**:

- [x] Load conversation list from `/v1/conversations` on startup
- [x] Populate ThreadList sidebar with existing conversations
- [x] Auto-select most recent conversation (or persist selection in localStorage)
- [x] Ensure thread switching loads messages from backend
- [x] Added 3 new E2E tests for persistence behavior:
  - `loads existing conversations from backend` - Tests thread list population
  - `auto-selects first conversation and loads its messages` - Tests auto-selection
  - `persists selected thread in localStorage` - Tests localStorage persistence

**Key implementation details**:

- Used `adapters.threadList` property of `useExternalStoreRuntime` to expose thread list to `ThreadListPrimitive`
- Thread list format: `{ id: string, title: string, status: "regular" }`
- Selected thread ID persisted to localStorage (`agent-cli-selected-thread` key)
- On mount: fetch conversations → populate thread list → auto-select saved or first thread
- All 8 E2E tests passing (5 original + 3 new persistence tests)

### Phase 4: Voice Integration (📅 Planned)

**Goal**: Voice input using browser MediaRecorder → backend transcription.

**Strategy**:

1. Custom "Record" button in Composer
2. Browser `MediaRecorder` API captures audio
3. POST to `/transcribe` endpoint
4. Inject transcribed text into Composer

### Phase 5: RAG Visualization (📅 Planned)

**Goal**: Show source citations and memory updates.

### Phase 6: Platform Wrappers (📅 Deferred)

**Goal**: Electron desktop app, iOS app.

**Note**: Web-first approach. Same codebase can be wrapped later with:
- Electron for desktop
- Capacitor/React Native for iOS

## 5. How to Run

### Prerequisites

```bash
# Terminal 1: Start backend services
agent-cli start-services

# Terminal 2: Start memory proxy
agent-cli memory-proxy
```

### Development (Web)

```bash
cd UI
bun install
bun run dev  # Opens http://localhost:5173
```

### Testing

```bash
cd UI
bun run test
```

## 6. Context for Next Agent

### Current State Summary

| Layer | Status | Notes |
|-------|--------|-------|
| Backend (`agent_cli/`) | 🟢 Solid | CORS enabled, conversation endpoints working |
| Infrastructure (`UI/`) | 🟢 Solid | Vite + React + TypeScript + Bun configured |
| Frontend (`UI/src/`) | 🟢 Completed | Using native assistant-ui primitives with runtime adapter |

### Backend State (KEEP - No Changes Needed)

The backend is ready. These files were added/modified and work correctly:

```
agent_cli/memory/api.py      # Added GET /v1/conversations, GET /v1/conversations/{id}
agent_cli/memory/client.py   # Added list_conversations(), get_history()
agent_cli/memory/_files.py   # Added load_conversation_history()
```

**Test the backend**:
```bash
curl http://localhost:8100/v1/conversations
curl http://localhost:8100/v1/conversations/default
```

### Frontend State (✅ COMPLETED)

**Current files in `UI/src/`**:

| File | Status | Description |
|------|--------|-------------|
| `App.tsx` | ✅ UPDATED | Uses `AssistantRuntimeProvider` with config state and SettingsModal |
| `runtime/useAgentCLIRuntime.ts` | ✅ UPDATED | Runtime adapter with useRef for dynamic config |
| `components/ThreadList.tsx` | ✅ UPDATED | Native thread list with Settings button |
| `components/Thread.tsx` | ✅ SIMPLIFIED | Wraps thread primitives for chat display |
| `components/SettingsModal.tsx` | ✅ NEW | Model and RAG parameter configuration |
| `main.tsx` | ✅ UNCHANGED | Entry point |
| `index.css` | ✅ UNCHANGED | Tailwind imports |

**Deleted files** (from previous phase):
- `components/Sidebar.tsx` - Replaced by `ThreadList.tsx`
- `components/ChatArea.tsx` - Logic moved to runtime

### Immediate Task: Phase 4 - Voice Integration

**Goal**: Voice input using browser MediaRecorder → backend transcription.

**Planned steps**:

1. **Add voice button** to the Composer area (next to Send button)

2. **Implement recording** using browser `MediaRecorder` API:
   - Start/stop recording on button press
   - Capture audio as WAV/WebM blob

3. **Create transcription endpoint** integration:
   - POST audio blob to `/transcribe` endpoint
   - Receive transcribed text

4. **Inject transcribed text** into Composer input field

**Backend requirement**: The `/transcribe` endpoint may need to be created if not already available.

### Key Reference Files (in `assistant-ui/` submodule)

**Must read before implementing**:

1. **LangGraph runtime hook** (best pattern to follow):
   ```
   assistant-ui/packages/react-langgraph/src/useLangGraphRuntime.tsx
   ```

2. **Thread list primitives**:
   ```
   assistant-ui/packages/react/src/primitives/threadList/index.ts
   assistant-ui/packages/react/src/primitives/threadListItem/index.ts
   ```

3. **Working example with thread list**:
   ```
   assistant-ui/examples/with-langgraph/app/MyRuntimeProvider.tsx
   assistant-ui/examples/with-langgraph/components/assistant-ui/thread-list.tsx
   ```

4. **Thread list types**:
   ```
   assistant-ui/packages/react/src/client/types/ThreadList.ts
   ```

### Gotchas and Tips

1. **SSE Streaming**: The memory-proxy returns SSE. The runtime's `stream` callback needs to parse this. Look at how LangGraph example handles streaming.

2. **Thread ID persistence**: Assistant-ui manages which thread is active. The runtime just needs to load/save to our backend.

3. **No need to list threads manually**: Once runtime is set up, `ThreadListPrimitive` automatically shows threads from the runtime's state.

4. **Install `@assistant-ui/react-langgraph`**: If using that pattern, add the dependency:
   ```bash
   cd UI && bun add @assistant-ui/react-langgraph
   ```

### Verification Checklist (Phase 2)

Test the following to verify Phase 2 implementation:

- [ ] Start backend: `agent-cli memory-proxy`
- [ ] Start UI: `cd UI && bun run dev`
- [ ] Open http://localhost:5173
- [ ] Can create new chat threads via "New Chat" button
- [ ] Thread list shows all conversations from backend
- [ ] Clicking a thread loads its history
- [ ] Sending a message works with streaming response
- [ ] Switching threads preserves history
- [ ] No manual `useState` for conversation management in React (verified in code)

## 7. Backend API Contract

### Existing Endpoints (Memory Proxy - Port 8100)

#### `POST /v1/chat/completions`
Chat with memory-augmented LLM.

```typescript
// Request
{
  messages: Array<{ role: "user" | "assistant", content: string }>,
  model?: string,           // e.g., "gpt-4o", "llama3"
  stream?: boolean,         // SSE streaming
  memory_id?: string,       // Conversation ID (default: "default")
  memory_top_k?: number,    // RAG context limit
  memory_recency_weight?: number,
  memory_score_threshold?: number
}

// Response (non-streaming)
{
  choices: [{ message: { role: "assistant", content: string } }]
}
```

#### `GET /v1/conversations`
List all conversation IDs.

```typescript
// Response
{
  conversations: string[]  // e.g., ["default", "chat-1234", "work-project"]
}
```

#### `GET /v1/conversations/{conversation_id}`
Get message history for a conversation.

```typescript
// Response
{
  messages: Array<{
    role: "user" | "assistant",
    content: string,
    // Note: Backend stores timestamps but format may vary
  }>
}
```

### Endpoints Needed (Future)

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `POST /v1/conversations` | Create new conversation | Phase 2 |
| `DELETE /v1/conversations/{id}` | Delete/archive conversation | Phase 2 |
| `PATCH /v1/conversations/{id}` | Rename conversation | Phase 3 |
| `POST /transcribe` | Voice transcription | Phase 4 |

---

## 8. Phase 2 Implementation Guide

### Step 1: Understand Assistant-UI Runtime Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 AssistantRuntimeProvider                     │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Runtime                               ││
│  │  ┌─────────────────┐  ┌─────────────────────────────┐  ││
│  │  │ ThreadListCore  │  │ ThreadCore                   │  ││
│  │  │                 │  │ ┌─────────────────────────┐  │  ││
│  │  │ • threadIds     │  │ │ MessageRepository       │  │  ││
│  │  │ • switchThread  │  │ │ • messages              │  │  ││
│  │  │ • createThread  │  │ │ • append                │  │  ││
│  │  └─────────────────┘  │ └─────────────────────────┘  │  ││
│  │                       │ ┌─────────────────────────┐  │  ││
│  │                       │ │ ComposerCore            │  │  ││
│  │                       │ │ • send                  │  │  ││
│  │                       │ └─────────────────────────┘  │  ││
│  │                       └─────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Step 2: Choose Integration Pattern

**Option A: `useLangGraphRuntime` pattern** (Recommended)
- Best documented example with thread list
- Has `create`, `load`, `stream` callbacks
- See: `assistant-ui/examples/with-langgraph/app/MyRuntimeProvider.tsx`

**Option B: `useExternalStoreRuntime` pattern**
- Lower level, more control
- Manages messages directly
- See: `assistant-ui/examples/with-external-store/`

**Option C: Custom Runtime Core**
- Most flexible but most complex
- Implement `ThreadListRuntimeCore` directly
- See: `assistant-ui/packages/react/src/legacy-runtime/runtime-cores/`

### Step 3: Create Runtime Hook

Create `UI/src/runtime/useAgentCLIRuntime.ts`:

```typescript
// Pseudocode - actual implementation depends on chosen pattern
import { useLangGraphRuntime } from "@assistant-ui/react-langgraph";
// OR
import { useExternalStoreRuntime } from "@assistant-ui/react";

const API_BASE = "http://localhost:8100";

export function useAgentCLIRuntime() {
  return useLangGraphRuntime({
    // Called when switching to a thread
    load: async (threadId: string) => {
      const res = await fetch(`${API_BASE}/v1/conversations/${threadId}`);
      const data = await res.json();
      return { messages: data.messages };
    },

    // Called when creating new thread
    create: async () => {
      const newId = `chat-${Date.now()}`;
      // Optionally POST to create on backend
      return { externalId: newId };
    },

    // Called when sending a message
    stream: async function* (messages, { threadId }) {
      const res = await fetch(`${API_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages,
          memory_id: threadId,
          stream: true,
        }),
      });
      // Handle SSE streaming...
      yield* parseSSEStream(res);
    },
  });
}
```

### Step 4: Refactor App.tsx

```typescript
// UI/src/App.tsx
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { ThreadList } from "./components/ThreadList";  // Uses primitives
import { Thread } from "./components/Thread";          // Uses primitives
import { useAgentCLIRuntime } from "./runtime/useAgentCLIRuntime";

export default function App() {
  const runtime = useAgentCLIRuntime();

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-screen">
        <ThreadList />   {/* Native ThreadListPrimitive */}
        <Thread />       {/* Native ThreadPrimitive */}
      </div>
    </AssistantRuntimeProvider>
  );
}
```

### Step 5: Create ThreadList Component Using Primitives

```typescript
// UI/src/components/ThreadList.tsx
import { ThreadListPrimitive, ThreadListItemPrimitive } from "@assistant-ui/react";

export const ThreadList = () => (
  <ThreadListPrimitive.Root className="w-64 border-r">
    <ThreadListPrimitive.New>
      <button>+ New Chat</button>
    </ThreadListPrimitive.New>
    <ThreadListPrimitive.Items components={{ ThreadListItem }} />
  </ThreadListPrimitive.Root>
);

const ThreadListItem = () => (
  <ThreadListItemPrimitive.Root>
    <ThreadListItemPrimitive.Trigger>
      <ThreadListItemPrimitive.Title fallback="New Chat" />
    </ThreadListItemPrimitive.Trigger>
  </ThreadListItemPrimitive.Root>
);
```

### Step 6: Delete Custom Components

After refactoring, remove:
- [ ] `UI/src/components/Sidebar.tsx`
- [ ] `UI/src/components/ChatArea.tsx`
- [ ] `UI/src/components/SettingsModal.tsx` (keep for Phase 3 if RAG settings needed)

---

## 9. Assistant-UI Reference Paths

### Key Source Files (in `assistant-ui/` submodule)

| What | Path |
|------|------|
| ThreadList primitives | `packages/react/src/primitives/threadList/` |
| ThreadListItem primitives | `packages/react/src/primitives/threadListItem/` |
| Runtime core interfaces | `packages/react/src/legacy-runtime/runtime-cores/core/` |
| LangGraph runtime | `packages/react-langgraph/src/useLangGraphRuntime.tsx` |
| External store runtime | `packages/react/src/legacy-runtime/runtime-cores/external-store/` |
| Thread history adapter | `packages/react/src/legacy-runtime/runtime-cores/adapters/thread-history/` |
| Model context types | `packages/react/src/model-context/ModelContextTypes.ts` |

### Key Examples

| Example | Demonstrates |
|---------|--------------|
| `examples/with-langgraph/` | Thread list + custom backend |
| `examples/with-external-store/` | Full message control |
| `examples/with-cloud/` | Thread list UI styling |
| `examples/with-ai-sdk-v5/` | AI SDK integration |

### Key Interfaces to Study

```typescript
// From packages/react/src/client/types/ThreadList.ts
type ThreadListClientApi = {
  getState(): ThreadListClientState;
  switchToThread(threadId: string): void;
  switchToNewThread(): void;
  // ...
};

// From packages/react/src/model-context/ModelContextTypes.ts
type LanguageModelConfig = {
  apiKey?: string;
  baseUrl?: string;
  modelName?: string;
};
```

---

## 10. Anti-Patterns to Avoid

❌ **Don't** manually manage thread list state in React
✅ **Do** implement runtime adapter that assistant-ui controls

❌ **Don't** build custom Sidebar component
✅ **Do** use `ThreadListPrimitive.Root`, `ThreadListPrimitive.Items`

❌ **Don't** create separate `AssistantRuntimeProvider` per conversation
✅ **Do** use single provider with runtime that handles switching

❌ **Don't** treat assistant-ui as just a "message renderer"
✅ **Do** leverage its full runtime system for state management

❌ **Don't** fetch conversation list in `useEffect` with manual state
✅ **Do** implement `load` callback that runtime calls when needed

---

## 11. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-11-24 | Web-first, defer Electron | Simpler development, same code works everywhere |
| 2025-11-24 | Use assistant-ui primitives over custom components | Native features (thread list, model context) reduce custom code |
| 2025-11-24 | Add assistant-ui as submodule | AI reference for understanding interfaces |
| 2025-11-24 | Pivot from custom Sidebar to ThreadListPrimitive | Wrong path identified, correcting |
| 2025-11-24 | Keep backend, refactor frontend only | Backend API is solid; only UI layer needs correction |
| 2025-11-24 | Use `useLangGraphRuntime` pattern | Best documented approach with thread list support |
| 2025-11-24 | Remove markdown dependency temporarily | Type compatibility issues; plain text works for MVP |
| 2025-11-24 | Delete SettingsModal for now | Defer to Phase 3; focus on core thread list functionality first |
| 2025-11-24 | Recreate SettingsModal with model/RAG config | Phase 3 implementation with dynamic runtime config |
| 2025-11-24 | Use useRef for config in runtime | Avoid stale closure issues when config changes |
| 2025-11-25 | Fetch models from `/v1/models` API | Dynamic model list instead of hardcoding |
| 2025-11-25 | Replace `useLangGraphRuntime` with `useExternalStoreRuntime` | `useLangGraphRuntime` requires AssistantCloud; `useExternalStoreRuntime` gives full control without cloud dependency |
| 2025-11-25 | Add Playwright E2E tests | Enable automated testing instead of manual verification |
| 2025-11-25 | Support `reasoning_content` in SSE parser | Thinking models (qwen3-thinking) use this field instead of `content` |
| 2025-11-25 | Use `adapters.threadList` for thread list data | Proper API for exposing thread list to `ThreadListPrimitive` primitives |
| 2025-11-25 | Persist selected thread in localStorage | Enable conversation continuity across page refreshes |
| 2025-11-25 | Auto-select first conversation on startup | Better UX when returning to app with existing conversations |

---

## 12. Open Questions

- [x] Which runtime pattern works best with our backend? → **`useLangGraphRuntime`** (implemented)
- [x] Do we need `POST /v1/conversations` to create threads? → **No, lazy creation works** (implemented)
- [x] How to handle SSE streaming from memory-proxy? → **Custom SSE parser in `parseSSEStream`** (implemented)
- [x] Should settings (model, RAG params) persist in localStorage or backend? → **React state for now** (session-only; localStorage can be added later)
- [ ] How to handle thread titles? (Currently shows "New Chat" fallback)
- [ ] Add thread deletion/archiving support?
- [ ] Add more RAG parameters to settings? (score_threshold, recency_weight)
