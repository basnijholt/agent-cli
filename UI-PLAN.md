# UI Development Plan: Agent CLI Desktop

> **Status**: Active / Phase 2 In Progress (Pivot)
> **Last Updated**: 2025-11-24

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

### Phase 2: Native Thread List Integration (🚧 IN PROGRESS - PIVOT)

**Goal**: Multi-session chat using assistant-ui's native `ThreadListPrimitive`.

**What to do**:

1. **Create `useAgentCLIRuntime` hook** that implements:
   - `ThreadListRuntimeCore` interface for thread listing/switching
   - `ThreadHistoryAdapter` interface for message persistence
   - Connection to existing backend endpoints

2. **Refactor `App.tsx`** to use:
   - `ThreadListPrimitive` for sidebar (native, not custom)
   - `ThreadPrimitive` for chat view
   - Single `AssistantRuntimeProvider` with our runtime

3. **Delete custom components** (replace with primitives):
   - `Sidebar.tsx` → `ThreadListPrimitive`
   - `ChatArea.tsx` → Inline in App with runtime
   - Keep `Thread.tsx` if it just wraps primitives nicely

**Reference**: See `assistant-ui/examples/with-langgraph/` for thread list pattern.

### Phase 3: Model & Settings (📅 Planned)

**Goal**: Switch models and configure RAG parameters.

**Strategy**:

1. Use `ModelContext` to pass model configuration to API
2. Create minimal Settings UI that updates `ModelContext`
3. Backend can proxy `/v1/models` or we hardcode available models

**Note**: Settings modal may remain custom since RAG-specific options (top_k, memory parameters) aren't standard in assistant-ui.

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

### Current State

- App has basic chat working
- Backend has conversation list/history endpoints
- **PIVOT NEEDED**: Current frontend uses custom components (Sidebar, ChatArea) instead of native assistant-ui primitives

### Immediate Task

**Implement Phase 2**: Create `useAgentCLIRuntime` hook that implements assistant-ui's thread list interface, then refactor App to use `ThreadListPrimitive`.

### Key Files

- `UI/src/App.tsx` - Main entry, needs refactor
- `UI/src/components/` - Custom components, mostly to be replaced
- `agent_cli/memory/api.py` - Backend API (good, keep)
- `assistant-ui/` - Reference submodule for understanding runtime interfaces

### Assistant-UI Reference

The `assistant-ui/` directory is a **reference submodule** for understanding:
- `packages/react/src/primitives/threadList/` - ThreadList primitives
- `packages/react/src/legacy-runtime/runtime-cores/` - Runtime core implementations
- `examples/with-langgraph/` - Thread list example
- `examples/with-external-store/` - Custom backend example

Key interfaces to implement:
- `ThreadListRuntimeCore` (or use external store pattern)
- `ThreadHistoryAdapter` for message persistence
- `ModelContext` for configuration

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
| 2024-11-24 | Web-first, defer Electron | Simpler development, same code works everywhere |
| 2024-11-24 | Use assistant-ui primitives over custom components | Native features (thread list, model context) reduce custom code |
| 2024-11-24 | Add assistant-ui as submodule | AI reference for understanding interfaces |
| 2024-11-24 | Pivot from custom Sidebar to ThreadListPrimitive | Wrong path identified, correcting |

---

## 12. Open Questions

- [ ] Which runtime pattern works best with our backend? (LangGraph vs External Store)
- [ ] Do we need `POST /v1/conversations` to create threads, or can we create lazily?
- [ ] How to handle SSE streaming from memory-proxy in the runtime?
- [ ] Should settings (model, RAG params) persist in localStorage or backend?
