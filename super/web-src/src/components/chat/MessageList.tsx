import type { ChatMessage } from '../../types';
import { Button } from '../ui/Button';
import { Alert } from '../ui/Alert';
import { MessageItem } from './MessageItem';
import { EmptyState } from './EmptyState';

type Props = {
  messages: ChatMessage[];
  busy: boolean;
  loading?: boolean;
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
  onSendSuggestion?: (v: string) => void;
  onClearError: () => void;
  onApprovalsChange?: (idx: number, approvals: import('../../types').ApprovalRequest[]) => void;
  bottomRef: React.RefObject<HTMLDivElement | null>;
};

export function MessageList({
  messages, busy, loading, error, editingIdx, editDraft, setEditDraft, setEditingIdx,
  onEditAndResend, onCopy, onEdit, onBranch, onRegenerate, onStop,
  onSetInput, onSendSuggestion, onClearError, onApprovalsChange, bottomRef,
}: Props) {
  return (
    <div className="message-list" aria-live="polite" aria-relevant="additions text">
      <div className="message-list-inner">
        {messages.length === 0 && loading && (
          <div className="muted small" style={{ padding: 'var(--space-6) var(--space-2)' }} role="status">
            Loading chat…
          </div>
        )}
        {messages.length === 0 && !busy && !loading && (
          <EmptyState onPick={(s) => { if (onSendSuggestion) onSendSuggestion(s); else onSetInput(s); }} />
        )}
        {busy && (
          <div className="sr-only" role="status">Reply in progress. Press Stop to cancel.</div>
        )}
        {messages.map((m, i) => (
          <MessageItem
            key={`${m.role}-${m.ts}-${i}`}
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
            onApprovalsChange={onApprovalsChange}
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
    </div>
  );
}
