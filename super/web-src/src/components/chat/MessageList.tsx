import type { ChatMessage } from '../../types';
import { Button } from '../ui/Button';
import { Alert } from '../ui/Alert';
import { MessageItem } from './MessageItem';
import { EmptyState } from './EmptyState';

type Props = {
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  editingIdx: number | null;
  editDraft: string;
  setEditDraft: (v: string) => void;
  setEditingIdx: (v: number | null) => void;
  onEditAndResend: (idx: number) => void;
  onCopy: (content: string) => void;
  onEdit: (idx: number) => void;
  onBranch: (idx: number) => void;
  onRegenerate: (idx: number) => void;
  onStop: () => void;
  onSetInput: (v: string) => void;
  onClearError: () => void;
  bottomRef: React.RefObject<HTMLDivElement | null>;
};

export function MessageList({ messages, busy, error, editingIdx, editDraft, setEditDraft, setEditingIdx, onEditAndResend, onCopy, onEdit, onBranch, onRegenerate, onStop, onSetInput, onClearError, bottomRef }: Props) {
  return (
    <div style={{ flex: 1, overflow: 'auto', padding: 'var(--space-4)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', background: 'var(--bg-2)' }}>
      {messages.length === 0 && !busy && <EmptyState onPick={onSetInput} />}
      {messages.map((m, i) => (
        <MessageItem
          key={i}
          message={m}
          index={i}
          busy={busy}
          isLast={i === messages.length - 1}
          editingIdx={editingIdx}
          editDraft={editDraft}
          setEditDraft={setEditDraft}
          setEditingIdx={setEditingIdx}
          onEditAndResend={onEditAndResend}
          onCopy={onCopy}
          onEdit={onEdit}
          onBranch={onBranch}
          onRegenerate={onRegenerate}
          onStop={onStop}
        />
      ))}
      {error && (
        <Alert variant="error" style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ marginTop: 2, flexShrink: 0 }} aria-hidden><circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 7v3M8 5.5h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
          <span style={{ flex: 1 }}>{error}</span>
          <Button size="sm" variant="ghost" onClick={onClearError}>dismiss</Button>
        </Alert>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
