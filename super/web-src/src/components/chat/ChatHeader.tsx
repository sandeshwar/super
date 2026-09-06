import { useState } from 'react';
import type { ChatMessage, SessionSummary } from '../../types';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Avatar } from './Avatar';
import { shortId } from '../../utils/format';

type Props = {
  activeId: string | null;
  activeMeta: SessionSummary | null;
  messages: ChatMessage[];
  isRenaming: boolean;
  onRename: (id: string, title: string | null) => void;
  onShare: (fmt: 'md' | 'json') => void;
  busy: boolean;
};

export function ChatHeader({ activeId, activeMeta, messages, isRenaming, onRename, onShare, busy }: Props) {
  const [headerEditing, setHeaderEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  return (
    <div style={{ padding: 'var(--space-2) var(--space-4)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'var(--bg-2)', flexShrink: 0 }}>
      <Avatar role="assistant" />
      <div style={{ lineHeight: 1.2, flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 'var(--text-base)', color: 'var(--fg-0)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
          {headerEditing && activeId ? (
            <input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { void onRename(activeId, editTitle); setHeaderEditing(false); }
                if (e.key === 'Escape') setHeaderEditing(false);
              }}
              onBlur={() => setHeaderEditing(false)}
              autoFocus
              placeholder="New title…"
              style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-base)', padding: '4px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--accent-border)', background: 'var(--bg-1)', color: 'var(--fg-0)' }}
            />
          ) : (
            <span className="truncate" style={{ flex: 1, minWidth: 0 }}>{activeMeta?.title || (activeId ? `Chat ${shortId(activeId, 8)}` : 'New conversation')}</span>
          )}
          {activeId && !headerEditing && (
            <>
              <button
                onClick={() => { setEditTitle(activeMeta?.title || ''); setHeaderEditing(true); }}
                title="Rename chat"
                aria-label="Rename chat"
                style={{ width: 26, height: 26, display: 'grid', placeItems: 'center', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)', background: 'var(--bg-1)', color: 'var(--fg-2)', cursor: 'pointer', flexShrink: 0 }}
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M11.5 2.5l2 2-7 7H4.5v-2l7-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
              </button>
              <button
                onClick={() => void onRename(activeId, null)}
                disabled={isRenaming || !messages.length}
                title={messages.length ? "Auto-rename via chat summary" : "Need messages to summarize"}
                aria-label="Auto-rename via summary"
                style={{ width: 26, height: 26, display: 'grid', placeItems: 'center', borderRadius: 'var(--radius-xs)', border: '1px solid var(--accent-border)', background: isRenaming ? 'var(--accent)' : 'var(--accent-soft)', color: isRenaming ? 'var(--accent-fg)' : 'var(--accent)', cursor: isRenaming || !messages.length ? 'not-allowed' : 'pointer', opacity: isRenaming || !messages.length ? 0.6 : 1, flexShrink: 0 }}
              >
                {isRenaming ? <span className="spin" style={{ width: 12, height: 12, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: 999, display: 'inline-block' }} /> : <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 2l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M13 3l.6 1.2L15 4.8l-1.4.6L13 6.8l-.6-1.4L11 4.8l1.4-.6L13 3z" stroke="currentColor" strokeWidth="1"/></svg>}
              </button>
            </>
          )}
          {activeId && <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)', flexShrink: 0 }}>{shortId(activeId, 8)}</Badge>}
          <Badge variant="accent" style={{ fontSize: 'var(--text-2xs)', flexShrink: 0 }}><span className="badge-dot" aria-hidden /> Best-of-5</Badge>
        </div>
        <div className="small muted" style={{ fontSize: 'var(--text-xs)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span>{messages.length ? `${messages.length} messages · streaming via /api/chat/stream` : 'Model sees current leaf + verified memory automatically'}</span>
          {activeId && messages.length > 0 && <span className="mono" style={{ marginLeft: 'auto', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>✦ auto-rename available</span>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <Button size="sm" variant="ghost" onClick={() => onShare('md')} title="Export md" disabled={!messages.length}>share</Button>
        <span className="mono small muted" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: busy ? 'var(--yellow)' : 'var(--green)', display: 'inline-block' }} aria-hidden />{busy ? 'streaming…' : 'ready'}</span>
      </div>
    </div>
  );
}
