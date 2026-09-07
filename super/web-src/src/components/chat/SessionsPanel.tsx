import type { ChildSpan, SessionSummary } from '../../types';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Card } from '../ui/Card';
import { SessionRow } from './SessionRow';

type Props = {
  sessions: SessionSummary[];
  filtered: SessionSummary[];
  activeId: string | null;
  /** Parent session id when viewing a nested agent transcript. */
  parentId?: string | null;
  activeSpanId?: string | null;
  filter: string;
  busy?: boolean;
  selectMode: boolean;
  selectedIds: Set<string>;
  onFilter: (v: string) => void;
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onSelectSpan?: (parentId: string, span: ChildSpan) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string | null) => void;
  onToggleSelectMode: () => void;
  onToggleSelected: (id: string) => void;
  onSelectAllFiltered: () => void;
  onClearSelection: () => void;
  onDeleteSelected: () => void;
};

export function SessionsPanel({
  sessions, filtered, activeId, parentId, activeSpanId, filter, busy,
  selectMode, selectedIds,
  onFilter, onNewChat, onSelect, onSelectSpan, onDelete, onRename,
  onToggleSelectMode, onToggleSelected, onSelectAllFiltered, onClearSelection, onDeleteSelected,
}: Props) {
  const nSel = selectedIds.size;
  return (
    <Card className="sessions-panel">
      <div className="sessions-panel-head">
        <Button variant="primary" size="sm" block onClick={onNewChat} style={{ justifyContent: 'center' }}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          New chat
        </Button>
        <div style={{ position: 'relative' }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-4)', pointerEvents: 'none' }} aria-hidden><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2"/><path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          <Input value={filter} onChange={(e) => onFilter(e.target.value)} placeholder="Filter chats…" style={{ paddingLeft: 28, fontSize: 'var(--text-sm)', background: 'var(--bg-1)' }} aria-label="Filter chats" />
        </div>
        <div className="sessions-panel-toolbar">
          <Button size="sm" variant={selectMode ? 'primary' : 'ghost'} onClick={onToggleSelectMode}>
            {selectMode ? 'Done' : 'Select'}
          </Button>
          {selectMode && (
            <>
              <Button size="sm" variant="ghost" onClick={onSelectAllFiltered} disabled={!filtered.length}>
                All
              </Button>
              <Button size="sm" variant="ghost" onClick={onClearSelection} disabled={!nSel}>
                None
              </Button>
              <Button
                size="sm"
                variant="danger"
                disabled={!nSel}
                onClick={() => {
                  if (confirm(`Delete ${nSel} chat${nSel !== 1 ? 's' : ''}? This cannot be undone.`)) onDeleteSelected();
                }}
              >
                Delete{nSel ? ` (${nSel})` : ''}
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="sessions-panel-list" role="list" aria-label="Chat list">
        {filtered.map((s) => {
          const spanOpen = parentId === s.id;
          return (
            <SessionRow
              key={s.id}
              s={s}
              active={s.id === activeId}
              childActive={spanOpen}
              activeSpanId={spanOpen ? activeSpanId : null}
              selectMode={selectMode}
              selected={selectedIds.has(s.id)}
              onSelect={() => onSelect(s.id)}
              onSelectSpan={(sp) => onSelectSpan?.(s.id, sp)}
              onToggleSelect={() => onToggleSelected(s.id)}
              onDelete={() => onDelete(s.id)}
              onRename={(t) => onRename(s.id, t)}
            />
          );
        })}
        {filtered.length === 0 && (
          <div className="empty" style={{ padding: 'var(--space-4)' }}>
            <div className="empty-icon" aria-hidden><svg viewBox="0 0 16 16" fill="none"><path d="M2.5 3.5a1 1 0 011-1h9a1 1 0 011 1v5.5a1 1 0 01-1 1H6.2l-1.9 1.9a.5.5 0 01-.8-.4V10h-1a1 1 0 01-1-1v-5.5z" stroke="currentColor" strokeWidth="1.2"/></svg></div>
            <p className="small muted">{filter ? 'No chats match filter' : 'No chats yet — start one'}</p>
          </div>
        )}
      </div>

      <div className="sessions-panel-foot panel-foot">
        <span className="mono">{sessions.length} chat{sessions.length !== 1 ? 's' : ''}{nSel ? ` · ${nSel} selected` : ''}</span>
        <span className="sessions-panel-status">
          <span className="dot" style={{ background: busy ? 'var(--yellow)' : 'var(--green)' }} aria-hidden />
          {busy ? 'writing…' : 'ready'}
        </span>
      </div>
    </Card>
  );
}
