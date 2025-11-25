// Shared types used across the application

export interface MessageMetadata {
  createdAt?: number;
  model?: string;
  systemFingerprint?: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  durationMs?: number;
  promptMs?: number;
  predictedMs?: number;
  promptPerSecond?: number;
  predictedPerSecond?: number;
  cacheTokens?: number;
}

export interface Model {
  id: string;
  object?: string;
  created?: number;
  owned_by?: string;
}
