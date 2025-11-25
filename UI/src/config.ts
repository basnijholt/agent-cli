export const API_BASE = "http://localhost:8100";

export const ENDPOINTS = {
  conversations: `${API_BASE}/v1/conversations`,
  chat: `${API_BASE}/v1/chat/completions`,
  models: `${API_BASE}/v1/models`,
} as const;
