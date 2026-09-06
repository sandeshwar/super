import type { SessionSummary } from '../../types';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Card } from '../ui/Card';
import { SessionRow } from './SessionRow';

type Props = {
  sessions: SessionSummary[];
  filtered: SessionSummary[];
  activeId: string | null;
  filter: string;
  onFilter: (v: string) => void;
  onNewChat: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string | null) => void;
};

export function SessionsPanel({ sessions, filtered, activeId, filter, onFilter, onNewChat, onSelect, onDelete, onRename }: Props) {
  return (
    <Card style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
      <div style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <Button variant="primary" size="sm" block onClick={onNewChat} style={{ justifyContent: 'center' }}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
          New chat
        </Button>
        <div style={{ position: 'relative' }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-4)', pointerEvents: 'none' }} aria-hidden><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2"/><path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          <Input value={filter} onChange={(e) => onFilter(e.target.value)} placeholder="Filter chats… /" style={{ paddingLeft: 28, fontSize: 'var(--text-sm)', background: 'var(--bg-1)' }} aria-label="Filter chats" />
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 'var(--space-1)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        {filtered.map((s) => (
          <SessionRow key={s.id} s={s} active={s.id === activeId} onSelect={() => onSelect(s.id)} onDelete={() => onDelete(s.id)} onRename={(t) => onRename(s.id, t)} />
        ))}
        {filtered.length === 0 && (
          <div className="empty" style={{ padding: 'var(--space-4)' }}>
            <div className="empty-icon" aria-hidden><svg viewBox="0 0 16 16" fill="none"><path d="M2.5 3.5a1 1 0 011-1h9a1 1 0 011 1v5.5a1 1 0 01-1 1H6.2l-1.9 1.9a.5.5 0 01-.8-.4V10h-1a1 1 0 01-1-1v-5.5z" stroke="currentColor" strokeWidth="1.2"/></svg></div>
            <p className="small muted">{filter ? 'No chats match filter' : 'No chats yet — start one'}</p>
          </div>
        )}
      </div>

      <div style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-1)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
        <span className="mono">{sessions.length} sessions</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}><span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--green)', display: 'inline-block' }} aria-hidden /> grounded</span>
      </div>
    </Card>
  );
}
