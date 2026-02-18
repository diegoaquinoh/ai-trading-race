/**
 * Models temporarily hidden from the frontend because we don't have API keys yet.
 *
 * ── How to re-enable ──
 * Remove the model string from HIDDEN_MODEL_TYPES below and the corresponding
 * entry from HIDDEN_AGENT_NAME_PREFIXES.  The agents will reappear on the
 * leaderboard, agent list, and equity chart immediately.
 *
 * TODO: Remove entries here once you have valid API keys for:
 *   - Llama  (Groq / Together.ai key)
 *   - Claude (Anthropic key)
 *   - Grok   (xAI key)
 */

/**
 * ModelProvider enum values (as returned by the .NET backend) that should be
 * hidden from every frontend view.
 */
export const HIDDEN_MODEL_TYPES: ReadonlySet<string> = new Set([
  'Llama',   // Groq / Together.ai – no API key yet
  'Claude',  // Anthropic – no API key yet
  'Grok',    // xAI – no API key yet
]);

/**
 * Agent name prefixes used by the /api/agents endpoint (AgentSummary),
 * which does NOT include modelType. We fall back to name-based matching.
 */
export const HIDDEN_AGENT_NAME_PREFIXES: readonly string[] = [
  'Llama',
  'Claude',
  'Grok',
];

/** Returns true if the entry should be SHOWN (i.e. not hidden). */
export function isVisibleModelType(modelType: string): boolean {
  return !HIDDEN_MODEL_TYPES.has(modelType);
}

/** Returns true if the agent name does NOT start with any hidden prefix. */
export function isVisibleAgentName(name: string): boolean {
  return !HIDDEN_AGENT_NAME_PREFIXES.some((prefix) =>
    name.startsWith(prefix),
  );
}
