import { useRef, useState, useCallback, useEffect } from "react";
import {
  useExternalStoreRuntime,
  useExternalMessageConverter,
  ThreadMessageLike,
} from "@assistant-ui/react";
import type { AppendMessage } from "@assistant-ui/react";

const API_BASE = "http://localhost:8100";

// Thread metadata
interface ThreadData {
  id: string;
  title: string;
}

// Storage key for persisting selected thread
const SELECTED_THREAD_KEY = "agent-cli-selected-thread";

// Message with stable ID and optional reasoning
interface MessageWithId {
  id: string;
  role: string;
  content: string;
  reasoning?: string;
}

// Generate unique message ID
let globalMessageId = 0;
function generateMessageId(): string {
  return `msg-${globalMessageId++}-${Date.now()}`;
}

// Content part types for assistant-ui
type ContentPart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string };

// Convert to assistant-ui format
function toThreadMessage(msg: MessageWithId): ThreadMessageLike {
  const content: ContentPart[] = [];

  // Add reasoning parts first (assistant-ui expects reasoning before text)
  if (msg.reasoning) {
    content.push({ type: "reasoning", text: msg.reasoning });
  }

  // Add text content
  if (msg.content) {
    content.push({ type: "text", text: msg.content });
  }

  // Ensure we always have at least one content part
  if (content.length === 0) {
    content.push({ type: "text", text: "" });
  }

  return {
    id: msg.id,
    role: msg.role === "user" ? "user" : "assistant",
    content,
  };
}

// Streaming state for SSE parsing
interface StreamingState {
  content: string;
  reasoning: string;
}

// Parse SSE stream from memory-proxy
async function* parseSSEStream(response: Response): AsyncGenerator<StreamingState> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  let accumulatedContent = "";
  let accumulatedReasoning = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") {
            return;
          }

          try {
            const parsed = JSON.parse(data);
            const choice = parsed.choices?.[0];
            const delta = choice?.delta;

            if (delta?.content) {
              accumulatedContent += delta.content;
            }
            if (delta?.reasoning_content) {
              accumulatedReasoning += delta.reasoning_content;
            }

            // Only yield if we have any content
            if (accumulatedContent || accumulatedReasoning) {
              yield {
                content: accumulatedContent,
                reasoning: accumulatedReasoning,
              };
            }

            if (choice?.finish_reason) {
              return;
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export interface AgentCLIRuntimeConfig {
  model?: string;
  memoryTopK?: number;
}

export function useAgentCLIRuntime(config: AgentCLIRuntimeConfig = {}) {
  const configRef = useRef(config);
  configRef.current = config;

  // Thread list state
  const [threads, setThreads] = useState<ThreadData[]>([]);
  const [isLoadingThreads, setIsLoadingThreads] = useState(true);

  // Get initial thread from localStorage or generate new
  const getInitialThreadId = () => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem(SELECTED_THREAD_KEY);
      if (saved) return saved;
    }
    return `chat-${Date.now()}`;
  };

  const [threadId, setThreadId] = useState<string>(getInitialThreadId);
  const [messages, setMessages] = useState<MessageWithId[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  // Track the streaming assistant message ID
  const streamingMessageIdRef = useRef<string | null>(null);

  // Persist selected thread to localStorage
  const persistThreadId = useCallback((id: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(SELECTED_THREAD_KEY, id);
    }
    setThreadId(id);
  }, []);

  // Fetch conversations from backend on mount
  useEffect(() => {
    const fetchConversations = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/conversations`);
        if (res.ok) {
          const data = await res.json();
          const conversations: string[] = data.conversations || [];

          // Convert to ThreadData format
          const threadList: ThreadData[] = conversations.map((id) => ({
            id,
            title: id, // Use ID as title for now
          }));
          setThreads(threadList);

          // If current threadId doesn't exist in the list and there are conversations,
          // switch to the first one or keep current if it was saved
          const savedThread = localStorage.getItem(SELECTED_THREAD_KEY);
          if (savedThread && conversations.includes(savedThread)) {
            // Load the saved thread's messages
            await loadThreadMessages(savedThread);
          } else if (conversations.length > 0) {
            // Auto-select the first conversation
            const firstThread = conversations[0];
            persistThreadId(firstThread);
            await loadThreadMessages(firstThread);
          }
          // If no conversations exist, keep the generated threadId for new chat
        }
      } catch (err) {
        console.error("Failed to fetch conversations:", err);
      } finally {
        setIsLoadingThreads(false);
      }
    };
    fetchConversations();
  }, []);

  // Load messages for a specific thread
  const loadThreadMessages = async (externalId: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/conversations/${externalId}`);
      if (res.ok) {
        const data = await res.json();
        const msgs: MessageWithId[] = (data.messages || []).map(
          (m: { role: string; content: string }, idx: number) => ({
            id: `loaded-${idx}-${Date.now()}`,
            role: m.role,
            content: m.content,
          })
        );
        setMessages(msgs);
      } else {
        setMessages([]);
      }
    } catch (error) {
      console.error("Error loading thread messages:", error);
      setMessages([]);
    }
  };

  // Convert messages to assistant-ui format
  const threadMessages = useExternalMessageConverter({
    callback: useCallback((msg: MessageWithId) => toThreadMessage(msg), []),
    messages,
    isRunning,
  });

  // Handle new message from user
  const onNew = useCallback(async (message: AppendMessage) => {
    const textParts = message.content.filter((p) => p.type === "text");
    const userText = textParts.map((p) => p.text).join("\n");
    if (!userText.trim()) return;

    // Create user message with unique ID
    const userMessage: MessageWithId = {
      id: generateMessageId(),
      role: "user",
      content: userText,
    };

    // Create assistant message placeholder with unique ID
    const assistantMessageId = generateMessageId();
    streamingMessageIdRef.current = assistantMessageId;

    setMessages((prev) => [...prev, userMessage]);
    setIsRunning(true);

    try {
      // Get current messages for API call (need to include the new user message)
      const apiMessages = [...messages, userMessage].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await fetch(`${API_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: apiMessages,
          memory_id: threadId,
          model: configRef.current.model,
          stream: true,
          memory_top_k: configRef.current.memoryTopK || 5,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      // Stream the response
      let finalState: StreamingState = { content: "", reasoning: "" };
      for await (const state of parseSSEStream(response)) {
        finalState = state;
        // Update or add the assistant message with both content and reasoning
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.id === assistantMessageId) {
            // Update existing streaming message
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: state.content,
                reasoning: state.reasoning || undefined,
              },
            ];
          } else {
            // Add new assistant message
            return [
              ...prev,
              {
                id: assistantMessageId,
                role: "assistant",
                content: state.content,
                reasoning: state.reasoning || undefined,
              },
            ];
          }
        });
      }

      // Ensure final message is set
      if (finalState.content || finalState.reasoning) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.id === assistantMessageId) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMsg,
                content: finalState.content,
                reasoning: finalState.reasoning || undefined,
              },
            ];
          }
          return prev;
        });
      }
    } catch (error) {
      console.error("Error streaming message:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMessageId,
          role: "assistant",
          content: `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setIsRunning(false);
      streamingMessageIdRef.current = null;
    }
  }, [messages, threadId]);

  // Create a new thread
  const switchToNewThread = useCallback(() => {
    const newId = `chat-${Date.now()}`;
    persistThreadId(newId);
    setMessages([]);
    setIsRunning(false);
    // Add new thread to list
    setThreads((prev) => {
      // Check if this thread already exists
      if (prev.some((t) => t.id === newId)) return prev;
      return [{ id: newId, title: "New Chat" }, ...prev];
    });
  }, [persistThreadId]);

  // Switch to existing thread
  const switchToThread = useCallback(async (externalId: string) => {
    persistThreadId(externalId);
    await loadThreadMessages(externalId);
    setIsRunning(false);
  }, [persistThreadId]);

  // Add current thread to list when first message is sent
  const addCurrentThreadToList = useCallback(() => {
    setThreads((prev) => {
      if (prev.some((t) => t.id === threadId)) return prev;
      return [{ id: threadId, title: "New Chat" }, ...prev];
    });
  }, [threadId]);

  // Wrap onNew to add thread to list
  const onNewWithThreadTracking = useCallback(
    async (message: AppendMessage) => {
      addCurrentThreadToList();
      await onNew(message);
    },
    [addCurrentThreadToList, onNew]
  );

  return useExternalStoreRuntime({
    isRunning,
    isLoading: isLoadingThreads,
    messages: threadMessages,
    onNew: onNewWithThreadTracking,
    adapters: {
      threadList: {
        threadId,
        threads: threads.map((t) => ({
          id: t.id,
          title: t.title,
          status: "regular" as const,
        })),
        onSwitchToNewThread: switchToNewThread,
        onSwitchToThread: switchToThread,
      },
    },
  });
}
