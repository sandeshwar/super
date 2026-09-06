import type { ChatMessage } from '../../types';
import { Button } from '../ui/Button';
import { Avatar } from './Avatar';
import { GateChip } from './GateChip';
import { MessageActions } from './MessageActions';
import { MessageBubble } from './MessageBubble';
import { formatTime } from '../../utils/format';

type Props = {
  message: ChatMessage;
  index: number;
  busy: boolean;
  isLast: boolean;
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
};

export function MessageItem({ message, index, busy, isLast, editingIdx, editDraft, setEditDraft, setEditingIdx, onEditAndResend, onCopy, onEdit, onBranch, onRegenerate, onStop }: Props) {
  const isUser = message.role === 'user';
  return (
    <div className="msg-wrap fade-in" style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start', alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '84%', flexDirection: isUser ? 'row-reverse' : 'row', overflow: 'visible', position: 'relative' }}>
      <Avatar role={message.role} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', alignItems: isUser ? 'flex-end' : 'flex-start', flex: 1, minWidth: 0, overflow: 'visible' }}>
        {editingIdx === index ? (
          <div style={{ width: '100%', display: 'flex', gap: 6, flexDirection: 'column' }}>
            <textarea value={editDraft} onChange={(e) => setEditDraft(e.target.value)} style={{ width: '100%', minHeight: 60, padding: 'var(--space-2)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--accent-border)', background: 'var(--bg-1)', color: 'var(--fg-0)', fontSize: 'var(--text-base)' }} />
            <div style={{ display: 'flex', gap: 6 }}>
              <Button size="sm" variant="primary" onClick={() => void onEditAndResend(index)}>save & resend</Button>
              <Button size="sm" variant="ghost" onClick={() => setEditingIdx(null)}>cancel</Button>
            </div>
          </div>
        ) : (
          <MessageBubble message={message} busy={busy} isLast={isLast} />
        )}
        <div style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' }}>
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-4)', whiteSpace: 'nowrap' }}>{isUser ? 'you' : 'super'} · {formatTime(message.ts) || (busy && isLast ? 'now' : '')}</span>
          {message.role === 'assistant' && <GateChip gate={message.gate} />}
        </div>
        <MessageActions
          message={message}
          index={index}
          role={message.role}
          busy={busy}
          isLast={isLast}
          onCopy={onCopy}
          onEdit={onEdit}
          onBranch={onBranch}
          onRegenerate={onRegenerate}
          onStop={onStop}
        />
      </div>
    </div>
  );
}
