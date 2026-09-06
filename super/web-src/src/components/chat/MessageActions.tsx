import type { ChatMessage } from '../../types';

type Props = {
  message: ChatMessage;
  index: number;
  role: string;
  busy: boolean;
  isLast: boolean;
  onCopy: (content: string) => void;
  onEdit: (idx: number) => void;
  onBranch: (idx: number) => void;
  onRegenerate: (idx: number) => void;
  onStop: () => void;
};

export function MessageActions({ message, index, role, busy, isLast, onCopy, onEdit, onBranch, onRegenerate, onStop }: Props) {
  return (
    <div className="msg-actions" role="group" aria-label="Message actions" style={{ justifyContent: role === 'user' ? 'flex-end' : 'flex-start' }}>
      {message.content && (
        <button className="btn btn-sm" onClick={() => onCopy(message.content)} title="Copy message" aria-label="Copy message">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><rect x="5" y="5" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.2"/><path d="M11 5V3.5a1 1 0 00-1-1H4a1 1 0 00-1 1V9a1 1 0 001 1H5" stroke="currentColor" strokeWidth="1.2"/></svg>
          copy
        </button>
      )}
      {role === 'user' && (
        <button className="btn btn-sm" onClick={() => onEdit(index)} title="Edit message" aria-label="Edit message">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M11.5 2.5l2 2-7 7H4.5v-2l7-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
          edit
        </button>
      )}
      <button className="btn btn-sm" onClick={() => onBranch(index)} title="Branch from here" aria-label="Branch from here">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M5 3v4.5a3 3 0 003 3h3M8 10l3 3-3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="5" cy="3" r="1.6" stroke="currentColor" strokeWidth="1.2"/><circle cx="11" cy="13" r="1.6" stroke="currentColor" strokeWidth="1.2"/><circle cx="8" cy="7.5" r="1.6" stroke="currentColor" strokeWidth="1.2"/></svg>
        branch
      </button>
      {role === 'assistant' && (
        <button className="btn btn-sm" onClick={() => onRegenerate(index)} title="Regenerate response" aria-label="Regenerate response">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3v2M8 11v2M3 8H5M11 8h2M4.2 4.2l1.4 1.4M10.4 10.4l1.4 1.4M4.2 11.8l1.4-1.4M10.4 5.6l1.4-1.4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          regenerate
        </button>
      )}
      {busy && isLast && role === 'assistant' && (
        <button className="btn btn-sm" onClick={onStop} title="Stop generation" aria-label="Stop generation" style={{ background: 'var(--red)', color: '#fff', borderColor: 'var(--red)' }}>
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden><rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor"/></svg>
          stop
        </button>
      )}
    </div>
  );
}
