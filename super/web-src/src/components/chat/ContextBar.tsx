import type { TaskNode } from '../../types';
import { Collapsible } from '../ui/Collapsible';

/** Context strip — collapsible so it costs one slim row when hidden. */
export function ContextBar({ tokenStats, leaf, messagesLen, cost }: { tokenStats: { total: number; limit: number; pct: number }; leaf: TaskNode | null; messagesLen: number; cost: { total: number } | null }) {
  const over = tokenStats.pct > 85;
  return (
    <div style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-1)', padding: '1px var(--space-1)' }}>
      <Collapsible
        title="Context"
        className="collapsible-bare"
        compact
        storageKey="chat-context"
        meta={
          <>
            <span className="mono" style={{ color: over ? 'var(--red)' : 'var(--fg-3)' }}>ctx {tokenStats.pct}%</span>
            <span className="mono">leaf {leaf?.id || 'none'}</span>
            {cost && <span className="mono">~{cost.total} tok</span>}
          </>
        }
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', paddingBottom: 'var(--space-2)' }}>
          <span className="mono">ctx {tokenStats.total}/{tokenStats.limit} · {tokenStats.pct}%</span>
          <div style={{ flex: 1, maxWidth: 200, height: 4, borderRadius: 99, background: 'var(--bg-4)', overflow: 'hidden' }}><div style={{ width: `${tokenStats.pct}%`, height: '100%', background: tokenStats.pct > 85 ? 'var(--red)' : tokenStats.pct > 60 ? 'var(--yellow)' : 'var(--accent)' }} /></div>
          <span className="mono">leaf {leaf?.id || 'none'} · {messagesLen} msgs</span>
          {cost && <span className="mono" style={{ marginLeft: 'auto' }}>cost ~{cost.total} tok</span>}
        </div>
      </Collapsible>
    </div>
  );
}
