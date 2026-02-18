/**
 * Models temporarily hidden from the frontend because we don't have API keys yet.
 *
 * ── How to re-enable ──
 * 1. Remove the model string from HIDDEN_MODEL_TYPES.
 * 2. Remove matching entries from HIDDEN_AGENT_NAME_PREFIXES.
 * The agents will reappear on the leaderboard, agent list, and equity chart
 * immediately — no backend change required.
 *
 * TODO: Remove entries here once you have valid API keys for:
 *   - Llama  (Groq / Together.ai key)
 *   - Mock   (Claude → Anthropic key, Grok → xAI key — currently seeded as Mock)
 */

/**
 * ModelProvider enum values (as returned by the .NET backend's
 * `agent.modelType` field) that should be hidden from every frontend view.
 *
 * "Mock" hides Claude & Grok (both seeded with ModelProvider.Mock).
 * "Llama" hides the Llama-70B agent.
 */
export const HIDDEN_MODEL_TYPES: ReadonlySet<string> = new Set([
  'Llama', // Groq / Together.ai – no API key yet
  'Mock',  // Claude (Anthropic) & Grok (xAI) – seeded as Mock, no keys yet
]);

/**
 * Agent name prefixes used by the /api/agents endpoint (AgentSummary),
 * which does NOT include modelType. We fall back to name-based matching
 * so the same agents are hidden on the Agents list page.
 */
export const HIDDEN_AGENT_NAME_PREFIXES: readonly string[] = [
  'Llama',   // Llama-70B
  'Claude',  // Claude (Mock provider)
  'Grok',    // Grok  (Mock provider)
];

/** Returns true when the leaderboard entry should be SHOWN (not hidden). */
export function isVisibleModelType(modelType: string): boolean {
  return !HIDDEN_MODEL_TYPES.has(modelType);
}

/** Returns true when the agent name should be SHOWN (not hidden). */
export function isVisibleAgentName(name: string): boolean {
  return !HIDDEN_AGENT_NAME_PREFIXES.some((prefix) =>
    name.startsWith(prefix),
  );
}
