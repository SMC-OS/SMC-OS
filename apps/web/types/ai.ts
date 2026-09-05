/**
 * GeoCore AI (Sprint 036, Workstream H).
 *
 * `engine` is the honesty mechanism. "llm" means a real model answered;
 * "builtin" means the deterministic catalogue assistant did, because no
 * AI provider is connected or the provider was unreachable. The UI shows
 * which, rather than presenting a keyword matcher as AI.
 */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  reply: string;
  engine: "llm" | "builtin";
  data?: unknown;
}

export interface AICapabilities {
  conversational: boolean;
  llm_configured: boolean;
  workspace_context: boolean;
  quote_drafting: boolean;
  material_search: boolean;
  notes: string[];
}
