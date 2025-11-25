import type { MessageMetadata } from "../types";

export interface StreamingState extends Omit<MessageMetadata, "createdAt" | "durationMs"> {
  content: string;
  reasoning: string;
}

export async function* parseSSEStream(response: Response): AsyncGenerator<StreamingState> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  const state: StreamingState = { content: "", reasoning: "" };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        const data = line.slice(6).trim();
        if (data === "[DONE]") return;

        try {
          const parsed = JSON.parse(data);
          const delta = parsed.choices?.[0]?.delta;

          // Accumulate content
          if (delta?.content) state.content += delta.content;
          if (delta?.reasoning_content) state.reasoning += delta.reasoning_content;

          // Capture metadata (first occurrence wins for model/fingerprint)
          if (parsed.model && !state.model) state.model = parsed.model;
          if (parsed.system_fingerprint && !state.systemFingerprint) {
            state.systemFingerprint = parsed.system_fingerprint;
          }

          // Usage data (usually in final chunk, overwrites)
          if (parsed.usage) {
            state.promptTokens = parsed.usage.prompt_tokens;
            state.completionTokens = parsed.usage.completion_tokens;
            state.totalTokens = parsed.usage.total_tokens;
          }

          // Timings (usually in final chunk, overwrites)
          if (parsed.timings) {
            state.promptMs = parsed.timings.prompt_ms;
            state.predictedMs = parsed.timings.predicted_ms;
            state.promptPerSecond = parsed.timings.prompt_per_second;
            state.predictedPerSecond = parsed.timings.predicted_per_second;
            state.cacheTokens = parsed.timings.cache_n;
          }

          yield { ...state };

          if (parsed.choices?.[0]?.finish_reason) return;
        } catch {
          // Skip invalid JSON
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
