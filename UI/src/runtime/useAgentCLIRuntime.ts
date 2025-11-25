import { useRef, useState, useCallback, useEffect } from "react";
import {
  useExternalStoreRuntime,
  useExternalMessageConverter,
  ThreadMessageLike,
} from "@assistant-ui/react";
import type { AppendMessage } from "@assistant-ui/react";
import { ENDPOINTS } from "../config";
import { parseSSEStream, type StreamingState } from "../utils/sse";
import type { ResponseMetadata } from "../types";

// Thread metadata
interface ThreadData {
  id: string;
  title: string;
}

// Storage key for persisting selected thread
const SELECTED_THREAD_KEY = "agent-cli-selected-thread";

/**
 * Message with stable ID and optional reasoning.
 * Mirrors Python: agent_cli.memory.entities.Turn (partially)
 */
interface MessageWithId {
  id: string;
  role: string;
  content: string;
  reasoning?: string;
  created_at?: string; // ISO timestamp from API (mirrors Turn.created_at)
  response_metadata?: ResponseMetadata; // Mirrors Turn.response_metadata
}

// Generate unique message ID
let globalMessageId = 0;
function generateMessageId(): string {
  return `msg-${globalMessageId++}-${Date.now()}`;
}

// Content part types for assistant-ui
type ContentPart = { type: "text"; text: string } | { type: "reasoning"; text: string };

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

  // Combine created_at and response_metadata into custom metadata for assistant-ui
  const customMetadata: Record<string, unknown> = {};
  if (msg.created_at) {
    customMetadata.created_at = msg.created_at;
  }
  if (msg.response_metadata) {
    Object.assign(customMetadata, msg.response_metadata);
  }

  return {
    id: msg.id,
    role: msg.role === "user" ? "user" : "assistant",
    content,
    metadata: Object.keys(customMetadata).length > 0 ? { custom: customMetadata } : undefined,
  };
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
        const res = await fetch(ENDPOINTS.conversations);
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
  }, [persistThreadId]);

  // Load messages for a specific thread
  const loadThreadMessages = async (externalId: string) => {
    try {
      const res = await fetch(`${ENDPOINTS.conversations}/${externalId}`);
      if (res.ok) {
        const data = await res.json();
        // LoadedMessage mirrors Python's API response structure
        interface LoadedMessage {
          role: string;
          content: string;
          created_at?: string;
          metadata?: ResponseMetadata;
        }
        const msgs: MessageWithId[] = (data.messages || []).map(
          (m: LoadedMessage, idx: number) => ({
            id: `loaded-${idx}-${Date.now()}`,
            role: m.role,
            content: m.content,
            created_at: m.created_at,
            response_metadata: m.metadata,
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
  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textParts = message.content.filter((p) => p.type === "text");
      const userText = textParts.map((p) => p.text).join("\n");
      if (!userText.trim()) return;

      // Create user message with unique ID and timestamp
      const userMessage: MessageWithId = {
        id: generateMessageId(),
        role: "user",
        content: userText,
        created_at: new Date().toISOString(),
      };

      // Create assistant message placeholder with unique ID
      const assistantMessageId = generateMessageId();
      streamingMessageIdRef.current = assistantMessageId;
      const startTime = Date.now();

      setMessages((prev) => [...prev, userMessage]);
      setIsRunning(true);

      try {
        // Get current messages for API call (need to include the new user message)
        const apiMessages = [...messages, userMessage].map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const response = await fetch(ENDPOINTS.chat, {
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

        // Calculate final metadata
        const durationMs = Date.now() - startTime;

        // Ensure final message is set with metadata
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
                  created_at: new Date(startTime).toISOString(),
                  response_metadata: {
                    model: finalState.model || configRef.current.model,
                    system_fingerprint: finalState.system_fingerprint,
                    prompt_tokens: finalState.prompt_tokens,
                    completion_tokens: finalState.completion_tokens,
                    total_tokens: finalState.total_tokens,
                    duration_ms: durationMs,
                    prompt_ms: finalState.prompt_ms,
                    predicted_ms: finalState.predicted_ms,
                    prompt_per_second: finalState.prompt_per_second,
                    predicted_per_second: finalState.predicted_per_second,
                    cache_tokens: finalState.cache_tokens,
                  },
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
            created_at: new Date(startTime).toISOString(),
          },
        ]);
      } finally {
        setIsRunning(false);
        streamingMessageIdRef.current = null;
      }
    },
    [messages, threadId]
  );

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
  const switchToThread = useCallback(
    async (externalId: string) => {
      persistThreadId(externalId);
      await loadThreadMessages(externalId);
      setIsRunning(false);
    },
    [persistThreadId]
  );

  // Add current thread to list when first message is sent
  const addCurrentThreadToList = useCallback(() => {
    setThreads((prev) => {
      if (prev.some((t) => t.id === threadId)) return prev;
      return [{ id: threadId, title: "New Chat" }, ...prev];
    });
  }, [threadId]);

  // Archive (delete) a thread
  const archiveThread = useCallback(
    async (externalId: string) => {
      try {
        const res = await fetch(`${ENDPOINTS.conversations}/${externalId}`, {
          method: "DELETE",
        });
        if (res.ok) {
          // Remove from local state
          setThreads((prev) => prev.filter((t) => t.id !== externalId));
          // If we deleted the current thread, switch to a new one
          if (externalId === threadId) {
            switchToNewThread();
          }
        }
      } catch (err) {
        console.error("Failed to delete conversation:", err);
      }
    },
    [threadId, switchToNewThread]
  );

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
        onArchive: archiveThread,
      },
    },
  });
}
