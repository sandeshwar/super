import { useState } from 'react';
import type { ChatMessage, SessionSummary } from '../../types';
import { Badge } from '../ui/Badge';
import { Avatar } from './Avatar';
import { shortId } from '../../utils/format';

type Props = {
  activeId: string | null;
  activeMeta: SessionSummary | null;
  messages: ChatMessage[];
  isRenaming: boolean;
  onRename: (id: string, title: string | null) => void;
  busy: boolean;
  agentView?: { parentId: string; agentName: string; role?: string } | null;
  onBackToParent?: () => void;
};

export function ChatHeader({
  activeId, activeMeta, messages, isRenaming, onRename, busy,
  agentView, onBackToParent,
}: Props) {
  const [headerEditing, setHeaderEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');

  const commitRename = () => {
    if (!activeId || agentView) { setHeaderEditing(false); return; }
    const next = editTitle.trim();
    const prev = (activeMeta?.title || '').trim();
    setHeaderEditing(false);
    if (next && next !== prev) void onRename(activeId, next);
  };

  return (
    <div className="chat-header">
      <Avatar role="assistant" />
      <div style={{ lineHeight: 1.2, flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 'var(--text-base)', color: 'var(--fg-0)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
          {agentView && (
            <button
              type="button"
              className="chat-header-icon-btn"
              onClick={() => onBackToParent?.()}
              title="Back to parent chat"
              aria-label="Back to parent chat"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          )}
          {headerEditing && activeId && !agentView ? (
            <input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename();
                if (e.key === 'Escape') setHeaderEditing(false);
              }}
              onBlur={() => commitRename()}
              autoFocus
              placeholder="New title…"
              style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-base)', padding: '4px 8px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--accent-border)', background: 'var(--bg-1)', color: 'var(--fg-0)' }}
            />
          ) : (
            <span className="truncate" style={{ flex: 1, minWidth: 0 }}>
              {agentView
                ? agentView.agentName
                : (activeMeta?.title || (activeId ? `Chat ${shortId(activeId, 8)}` : 'New conversation'))}
            </span>
          )}
          {agentView && (
            <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)', flexShrink: 0 }}>
              {agentView.role || 'agent'}
            </Badge>
          )}
          {activeId && !headerEditing && !agentView && (
            <>
              <button
                type="button"
                onClick={() => { setEditTitle(activeMeta?.title || ''); setHeaderEditing(true); }}
                title="Rename chat"
                aria-label="Rename chat"
                className="chat-header-icon-btn"
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M11.5 2.5l2 2-7 7H4.5v-2l7-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
              </button>
              <button
                type="button"
                onClick={() => void onRename(activeId, null)}
                disabled={isRenaming || !messages.length}
                title={messages.length ? 'Auto-rename from summary' : 'Need messages to summarize'}
                aria-label="Auto-rename from summary"
                className="chat-header-icon-btn"
                style={{
                  borderColor: 'var(--accent-border)',
                  background: isRenaming ? 'var(--accent)' : 'var(--accent-soft)',
                  color: isRenaming ? 'var(--accent-fg)' : 'var(--accent)',
                  cursor: isRenaming || !messages.length ? 'not-allowed' : 'pointer',
                  opacity: isRenaming || !messages.length ? 0.6 : 1,
                }}
              >
                {isRenaming ? <span className="spin" style={{ width: 12, height: 12, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: 999, display: 'inline-block' }} /> : <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 2l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M13 3l.6 1.2L15 4.8l-1.4.6L13 6.8l-.6-1.4L11 4.8l1.4-.6L13 3z" stroke="currentColor" strokeWidth="1"/></svg>}
              </button>
            </>
          )}
          {activeId && <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)', flexShrink: 0 }}>{shortId(activeId, 8)}</Badge>}
        </div>
        <div className="small muted" style={{ fontSize: 'var(--text-xs)', marginTop: 1 }}>
          <span className="truncate">
            {agentView
              ? 'Sub-agent transcript · click parent chat to continue'
              : (messages.length ? `${messages.length} messages` : 'Uses the current task and saved memory')}
          </span>
        </div>
      </div>
      <span className="mono small muted chat-header-status">
        <span className="dot" style={{ background: busy ? 'var(--yellow)' : 'var(--green)', animation: busy ? undefined : 'none' }} aria-hidden />
        {busy ? 'writing…' : 'ready'}
      </span>
    </div>
  );
}
