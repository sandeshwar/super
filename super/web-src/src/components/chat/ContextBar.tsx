import type { TaskNode } from '../../types';

export function ContextBar({ tokenStats, leaf, messagesLen, cost }: { tokenStats: { total: number; limit: number; pct: number }; leaf: TaskNode | null; messagesLen: number; cost: { total: number } | null }) {
  return (
    <div style={{ padding: '6px var(--space-4)', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-1)', display: 'flex', alignItems: 'center', gap: 'var(--space-3)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
      <span className="mono">ctx {tokenStats.total}/{tokenStats.limit} · {tokenStats.pct}%</span>
      <div style={{ flex: 1, maxWidth: 200, height: 4, borderRadius: 99, background: 'var(--bg-4)', overflow: 'hidden' }}><div style={{ width: `${tokenStats.pct}%`, height: '100%', background: tokenStats.pct > 85 ? 'var(--red)' : tokenStats.pct > 60 ? 'var(--yellow)' : 'var(--accent)' }} /></div>
      <span className="mono">leaf {leaf?.id || 'none'} · {messagesLen} msgs</span>
      {cost && <span className="mono" style={{ marginLeft: 'auto' }}>cost ~{cost.total} tok</span>}
    </div>
  );
}
