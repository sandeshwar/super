/**
 * Formatting utilities — pure functions, single responsibility.
 * No DOM, no fetch, only data in → string out.
 */

export function shortId(id: string, len = 6): string {
  if (!id) return '—';
  return id.slice(0, len);
}

export function formatTime(ts: string | undefined): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return ts;
  }
}

export function formatDate(ts: string | undefined): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleDateString();
  } catch {
    return ts;
  }
}

export function pct(n: number, d: number): number {
  if (!d) return 0;
  return Math.round((n / d) * 100);
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

export function truncate(s: string, max = 40): string {
  if (!s) return s;
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function modelShort(model: string): string {
  if (!model) return 'offline';
  const part = model.split('/').pop() ?? model;
  return truncate(part, 28);
}
