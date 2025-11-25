import { useRef, useState, useCallback } from "react";
import {
  useExternalStoreRuntime,
  useExternalMessageConverter,
  ThreadMessageLike,
} from "@assistant-ui/react";
import type { AppendMessage } from "@assistant-ui/react";

const API_BASE = "http://localhost:8100";

// Message with stable ID
interface MessageWithId {
  id: string;
  role: string;
  content: string;
}

// Generate unique message ID
let globalMessageId = 0;
function generateMessageId(): string {
  return `msg-${globalMessageId++}-${Date.now()}`;
}

// Convert to assistant-ui format
function toThreadMessage(msg: MessageWithId): ThreadMessageLike {
  return {
    id: msg.id,
    role: msg.role === "user" ? "user" : "assistant",
    content: [{ type: "text", text: msg.content }],
  };
}

// Parse SSE stream from memory-proxy
async function* parseSSEStream(response: Response): AsyncGenerator<string> {
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

            const displayContent = accumulatedContent || accumulatedReasoning;
            if (displayContent) {
              yield displayContent;
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

  const [threadId, setThreadId] = useState<string>(() => `chat-${Date.now()}`);
  const [messages, setMessages] = useState<MessageWithId[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  // Track the streaming assistant message ID
  const streamingMessageIdRef = useRef<string | null>(null);

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
      let assistantContent = "";
      for await (const chunk of parseSSEStream(response)) {
        assistantContent = chunk;
        // Update or add the assistant message
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.id === assistantMessageId) {
            // Update existing streaming message
            return [
              ...prev.slice(0, -1),
              { ...lastMsg, content: assistantContent },
            ];
          } else {
            // Add new assistant message
            return [
              ...prev,
              { id: assistantMessageId, role: "assistant", content: assistantContent },
            ];
          }
        });
      }

      // Ensure final message is set
      if (assistantContent) {
        setMessages((prev) => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.id === assistantMessageId) {
            return [
              ...prev.slice(0, -1),
              { ...lastMsg, content: assistantContent },
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
    setThreadId(`chat-${Date.now()}`);
    setMessages([]);
    setIsRunning(false);
  }, []);

  // Switch to existing thread
  const switchToThread = useCallback(async (externalId: string) => {
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
        setThreadId(externalId);
        setMessages(msgs);
      } else {
        setThreadId(externalId);
        setMessages([]);
      }
    } catch (error) {
      console.error("Error loading thread:", error);
      setThreadId(externalId);
      setMessages([]);
    }
    setIsRunning(false);
  }, []);

  return useExternalStoreRuntime({
    isRunning,
    messages: threadMessages,
    onNew,
    onSwitchToNewThread: switchToNewThread,
    onSwitchToThread: switchToThread,
  });
}
