/** Thinking / reasoning effort levels for Ollama + mlx-serve. */

export type ThinkLevel = 'off' | 'low' | 'medium' | 'high' | 'max';

export const THINK_LEVELS_GRADED: ThinkLevel[] = ['off', 'low', 'medium', 'high', 'max'];

export const THINK_LEVEL_LABELS: Record<ThinkLevel, string> = {
  off: 'Off',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  max: 'Max',
};

export function normalizeThinkLevel(raw: unknown, levels?: ThinkLevel[]): ThinkLevel {
  const allowed = levels?.length ? levels : THINK_LEVELS_GRADED;
  let level: ThinkLevel = 'medium';
  if (raw === false || raw === 'false' || raw === 'off' || raw === 0 || raw === '0') level = 'off';
  else if (raw === true || raw === 'true' || raw === 'on') level = 'medium';
  else if (typeof raw === 'string' && (THINK_LEVELS_GRADED as string[]).includes(raw)) {
    level = raw as ThinkLevel;
  }
  if (!allowed.includes(level)) {
    return allowed.find((l) => l !== 'off') || allowed[0] || 'off';
  }
  return level;
}

/** Value persisted to llm.think */
export function thinkToConfig(level: ThinkLevel): boolean | string {
  if (level === 'off') return false;
  return level;
}
