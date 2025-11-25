// Streaming state for SSE parsing
export interface StreamingState {
  content: string;
  reasoning: string;
  model?: string;
  systemFingerprint?: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  // Timings from API
  promptMs?: number;
  predictedMs?: number;
  promptPerSecond?: number;
  predictedPerSecond?: number;
  cacheTokens?: number;
}

// Parse SSE stream from memory-proxy
export async function* parseSSEStream(response: Response): AsyncGenerator<StreamingState> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";
  let accumulatedContent = "";
  let accumulatedReasoning = "";

  // Metadata state
  let model: string | undefined;
  let systemFingerprint: string | undefined;
  let promptTokens: number | undefined;
  let completionTokens: number | undefined;
  let totalTokens: number | undefined;
  let promptMs: number | undefined;
  let predictedMs: number | undefined;
  let promptPerSecond: number | undefined;
  let predictedPerSecond: number | undefined;
  let cacheTokens: number | undefined;

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

            // Capture model from first chunk or whenever available
            if (parsed.model && !model) {
              model = parsed.model;
            }

            // Capture system fingerprint
            if (parsed.system_fingerprint && !systemFingerprint) {
              systemFingerprint = parsed.system_fingerprint;
            }

            // Capture usage data (usually in final chunk)
            if (parsed.usage) {
              promptTokens = parsed.usage.prompt_tokens;
              completionTokens = parsed.usage.completion_tokens;
              totalTokens = parsed.usage.total_tokens;
            }

            // Capture timings (usually in final chunk)
            if (parsed.timings) {
              promptMs = parsed.timings.prompt_ms;
              predictedMs = parsed.timings.predicted_ms;
              promptPerSecond = parsed.timings.prompt_per_second;
              predictedPerSecond = parsed.timings.predicted_per_second;
              cacheTokens = parsed.timings.cache_n;
            }

            if (delta?.content) {
              accumulatedContent += delta.content;
            }
            if (delta?.reasoning_content) {
              accumulatedReasoning += delta.reasoning_content;
            }

            // Yield updated state
            // Note: We always yield the accumulated content/reasoning + latest metadata
            yield {
              content: accumulatedContent,
              reasoning: accumulatedReasoning,
              model,
              systemFingerprint,
              promptTokens,
              completionTokens,
              totalTokens,
              promptMs,
              predictedMs,
              promptPerSecond,
              predictedPerSecond,
              cacheTokens,
            };

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
