import { useEffect, useState } from 'react';
import type { SessionSummary } from '../../types';
import { shortId } from '../../utils/format';

export function SessionRow({ s, active, onSelect, onDelete, onRename }: { s: SessionSummary; active: boolean; onSelect: () => void; onDelete: () => void; onRename: (title: string | null) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(s.title);
  useEffect(() => { setDraft(s.title); }, [s.title]);
  return (
    <div className={`session-row${active ? ' active' : ''}${editing ? ' editing' : ''}`}>
      <button
        className="session-row-select"
        onClick={onSelect}
        style={{
          flex: '1 1 auto', minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', textAlign: 'left',
          padding: 'var(--space-1) var(--space-2)', borderRadius: 'var(--radius-xs)', cursor: 'pointer',
          background: 'transparent', border: 'none', color: active ? 'var(--fg-0)' : 'var(--fg-1)',
        }}
        aria-label={`Select ${s.title || s.id}`}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0, maxWidth: '100%' }}>
          <span className="mono" style={{ flexShrink: 0, fontSize: 'var(--text-2xs)', padding: '2px 6px', borderRadius: 'var(--radius-xs)', background: active ? 'var(--accent)' : 'var(--bg-3)', color: active ? 'var(--accent-fg)' : 'var(--fg-3)', border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}` }}>{shortId(s.id, 6)}</span>
          {editing ? (
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { onRename(draft); setEditing(false); }
                if (e.key === 'Escape') setEditing(false);
              }}
              onBlur={() => setEditing(false)}
              autoFocus
              onClick={(e) => e.stopPropagation()}
              style={{ flex: 1, fontSize: 'var(--text-base)', padding: '2px 6px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--accent-border)', background: 'var(--bg-1)', color: 'var(--fg-0)' }}
            />
          ) : (
            <span title={s.title} style={{ fontWeight: active ? 600 : 500, fontSize: 'var(--text-base)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: '1 1 auto', minWidth: 0 }}>{s.title || 'Untitled'}</span>
          )}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)', fontSize: 'var(--text-xs)', color: active ? 'var(--accent)' : 'var(--fg-3)' }}>
          <span className="mono">{s.n} messages</span>
          <span style={{ width: 3, height: 3, borderRadius: 'var(--radius-full)', background: 'var(--fg-4)' }} aria-hidden />
          <span className="truncate">{s.updated ? new Date(s.updated).toLocaleDateString() : ''}</span>
        </span>
      </button>
      <div className="session-row-actions" role="group" aria-label="Chat actions">
        <button
          className="session-row-btn"
          onClick={(e) => { e.stopPropagation(); setEditing((v) => !v); }}
          aria-label={`Rename ${s.title || s.id}`}
          title="Rename chat"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M11.5 2.5l2 2-7 7H4.5v-2l7-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
        </button>
        <button
          className="session-row-btn"
          onClick={(e) => { e.stopPropagation(); onRename(null); }}
          aria-label="Auto-rename via summary"
          title="Auto-rename via chat summary"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 2l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
        </button>
        <button
          className="session-row-btn session-row-delete"
          onClick={(e) => { e.stopPropagation(); if (confirm(`Delete chat "${s.title || s.id.slice(0,6)}"? This cannot be undone.`)) onDelete(); }}
          aria-label={`Delete ${s.title || s.id}`}
          title="Delete chat"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M4 4l8 8M12 4L4 12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M3.5 4.5h9M6 4.5V3.5a1 1 0 011-1h2a1 1 0 011 1V4.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
        </button>
      </div>
    </div>
  );
}
