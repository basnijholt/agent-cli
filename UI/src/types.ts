// Shared types used across the application
// These types mirror the Python models in agent_cli/memory/entities.py

/**
 * Metadata captured from an LLM response (for assistant turns).
 * Mirrors Python: agent_cli.memory.entities.ResponseMetadata
 */
export interface ResponseMetadata {
  model?: string;
  system_fingerprint?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  duration_ms?: number;
  prompt_ms?: number;
  predicted_ms?: number;
  prompt_per_second?: number;
  predicted_per_second?: number;
  cache_tokens?: number;
}

/**
 * Combined metadata for UI display.
 * Includes created_at (from Turn) and all ResponseMetadata fields.
 */
export interface DisplayMetadata extends ResponseMetadata {
  created_at?: string;
}

export interface Model {
  id: string;
  object?: string;
  created?: number;
  owned_by?: string;
}
