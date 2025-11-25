import { useRef } from "react";
import { useLangGraphRuntime, LangGraphMessagesEvent } from "@assistant-ui/react-langgraph";
import type { LangChainMessage } from "@assistant-ui/react-langgraph";

const API_BASE = "http://localhost:8100";

// Convert OpenAI-style message to LangChain format
function toLangChainMessage(msg: { role: string; content: string }): LangChainMessage {
  if (msg.role === "user") {
    return { type: "human", content: msg.content };
  } else if (msg.role === "assistant") {
    return { type: "ai", content: msg.content };
  } else if (msg.role === "system") {
    return { type: "system", content: msg.content };
  }
  // Default to human for unknown roles
  return { type: "human", content: msg.content };
}

// Convert LangChain message to OpenAI-style for API calls
function toOpenAIMessage(msg: LangChainMessage): { role: string; content: string } {
  if (msg.type === "human") {
    return { role: "user", content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content) };
  } else if (msg.type === "ai") {
    return { role: "assistant", content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content) };
  } else if (msg.type === "system") {
    return { role: "system", content: msg.content };
  }
  // Default for tool messages
  return { role: "assistant", content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content) };
}

// Parse SSE stream from memory-proxy and yield LangGraph events
async function* parseSSEStream(response: Response): AsyncGenerator<LangGraphMessagesEvent<LangChainMessage>> {
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
            // Final message - combine reasoning and content
            const finalContent = accumulatedContent || accumulatedReasoning;
            if (finalContent) {
              yield {
                event: "messages/complete",
                data: [{ type: "ai", content: finalContent }],
              };
            }
            return;
          }

          try {
            const parsed = JSON.parse(data);
            const choice = parsed.choices?.[0];
            const delta = choice?.delta;

            // Handle regular content
            if (delta?.content) {
              accumulatedContent += delta.content;
            }

            // Handle reasoning_content (for thinking models like qwen3-thinking)
            if (delta?.reasoning_content) {
              accumulatedReasoning += delta.reasoning_content;
            }

            // Yield partial message for streaming display
            // Prefer content, fall back to reasoning if no content yet
            const displayContent = accumulatedContent || accumulatedReasoning;
            if (displayContent) {
              yield {
                event: "messages/partial",
                data: [{ type: "ai", content: displayContent }],
              };
            }

            // Check if stream is complete
            if (choice?.finish_reason) {
              const finalContent = accumulatedContent || accumulatedReasoning;
              if (finalContent) {
                yield {
                  event: "messages/complete",
                  data: [{ type: "ai", content: finalContent }],
                };
              }
              return;
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    }

    // Handle case where stream ends without [DONE] or finish_reason
    const finalContent = accumulatedContent || accumulatedReasoning;
    if (finalContent) {
      yield {
        event: "messages/complete",
        data: [{ type: "ai", content: finalContent }],
      };
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
  // Use a ref to always have the latest config in callbacks
  // This avoids stale closure issues when config changes
  const configRef = useRef(config);
  configRef.current = config;

  return useLangGraphRuntime({
    // Load messages for an existing thread
    load: async (threadId: string) => {
      const res = await fetch(`${API_BASE}/v1/conversations/${threadId}`);
      if (!res.ok) {
        // Thread doesn't exist yet, return empty
        return { messages: [] };
      }
      const data = await res.json();
      const messages: LangChainMessage[] = (data.messages || []).map(toLangChainMessage);
      return { messages };
    },

    // Create a new thread
    create: async () => {
      const newId = `chat-${Date.now()}`;
      // The backend creates conversations lazily on first message,
      // so we just return the new ID
      return { externalId: newId };
    },

    // Stream a message to the backend
    stream: async function* (messages: LangChainMessage[], { initialize }) {
      const { externalId } = await initialize();
      if (!externalId) throw new Error("Thread not found");

      // Convert messages to OpenAI format for the API
      const openAIMessages = messages.map(toOpenAIMessage);

      const response = await fetch(`${API_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: openAIMessages,
          memory_id: externalId,
          model: configRef.current.model, // Required by backend
          stream: true,
          memory_top_k: configRef.current.memoryTopK || 5,
        }),
      });

      if (!response.ok) {
        throw new Error(`Chat API error: ${response.status}`);
      }

      yield* parseSSEStream(response);
    },
  });
}
