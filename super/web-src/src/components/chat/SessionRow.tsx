import { useEffect, useState } from 'react';
import type { ChildSpan, SessionSummary } from '../../types';

type Props = {
  s: SessionSummary;
  active: boolean;
  /** True when a nested child session from this chat is open. */
  childActive?: boolean;
  activeSpanId?: string | null;
  selected?: boolean;
  selectMode?: boolean;
  onSelect: () => void;
  onSelectSpan?: (span: ChildSpan) => void;
  onToggleSelect?: () => void;
  onDelete: () => void;
  onRename: (title: string | null) => void;
};

function spanLabel(sp: ChildSpan): string {
  const summary = (sp.summary || '').trim();
  if (summary) return summary;
  return sp.agent_name || sp.agent_id || 'agent';
}

function SpanSublist({
  spans, activeSpanId, onSelectSpan,
}: {
  spans: ChildSpan[];
  activeSpanId?: string | null;
  onSelectSpan?: (span: ChildSpan) => void;
}) {
  if (!spans.length) return null;
  const active = spans.filter((x) => x.status === 'running');
  const inactive = spans.filter((x) => x.status !== 'running');
  return (
    <ul className="session-span-list" aria-label="Sub-agents">
      {[...active, ...inactive].map((sp) => {
        const canOpen = Boolean(sp.child_session_id);
        const isActive = !!activeSpanId && (sp.span_id === activeSpanId || sp.child_session_id === activeSpanId);
        return (
          <li key={sp.span_id} style={{ listStyle: 'none', margin: 0, padding: 0, minWidth: 0 }}>
            <button
              type="button"
              className={`session-span-item ${sp.status}${isActive ? ' active' : ''}`}
              title={canOpen ? (sp.goal || spanLabel(sp)) : 'Transcript not available'}
              disabled={!canOpen}
              onClick={(e) => {
                e.stopPropagation();
                if (canOpen) onSelectSpan?.(sp);
              }}
            >
              <span className={`session-span-dot ${sp.status}`} aria-hidden />
              <span className="session-span-summary">{spanLabel(sp)}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function SessionRow({
  s, active, childActive, activeSpanId, selected, selectMode,
  onSelect, onSelectSpan, onToggleSelect, onDelete, onRename,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(s.title);
  useEffect(() => { setDraft(s.title); }, [s.title]);
  const spans = s.spans || [];
  const nLive = spans.filter((x) => x.status === 'running').length;
  const nDone = spans.filter((x) => x.status !== 'running').length;

  return (
    <div className={`session-row${active ? ' active' : ''}${childActive ? ' has-active-span' : ''}${editing ? ' editing' : ''}${selected ? ' selected' : ''}${selectMode ? ' select-mode' : ''}${spans.length ? ' has-spans' : ''}`}>
      <div className="session-row-main">
        {selectMode && (
          <label className="session-row-check" onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              checked={!!selected}
              onChange={() => onToggleSelect?.()}
              aria-label={`Select ${s.title || s.id}`}
            />
          </label>
        )}

        <button
          className="session-row-select"
          onClick={() => (selectMode ? onToggleSelect?.() : onSelect())}
          aria-label={`${selectMode ? 'Toggle' : 'Select'} ${s.title || s.id}`}
        >
          <span className="session-row-title">
            {editing ? (
              <input
                className="session-row-rename"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { onRename(draft); setEditing(false); }
                  if (e.key === 'Escape') setEditing(false);
                }}
                onBlur={() => setEditing(false)}
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="session-row-name" title={s.title}>{s.title || 'Untitled'}</span>
            )}
            {nLive > 0 && <span className="session-span-badge live" title="Active sub-agent">live</span>}
          </span>
          <span className="session-row-meta mono">
            <span>{s.n} msg{s.n !== 1 ? 's' : ''}</span>
            {nLive > 0 && <span className="session-row-meta-sep" aria-hidden />}
            {nLive > 0 && <span className="session-row-meta-live">{nLive} live</span>}
            {nDone > 0 && <span className="session-row-meta-sep" aria-hidden />}
            {nDone > 0 && <span>{nDone} done</span>}
          </span>
        </button>

        {!selectMode && (
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
              onClick={(e) => { e.stopPropagation(); if (confirm(`Delete chat "${s.title || s.id.slice(0, 6)}"? This cannot be undone.`)) onDelete(); }}
              aria-label={`Delete ${s.title || s.id}`}
              title="Delete chat"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M4 4l8 8M12 4L4 12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M3.5 4.5h9M6 4.5V3.5a1 1 0 011-1h2a1 1 0 011 1V4.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
            </button>
          </div>
        )}
      </div>
      <SpanSublist spans={spans} activeSpanId={activeSpanId} onSelectSpan={onSelectSpan} />
    </div>
  );
}
