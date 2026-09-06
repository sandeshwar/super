import type { ChatMessage } from '../../types';
import { Collapsible } from '../ui/Collapsible';
import { Markdown } from '../Markdown';

export function MessageBubble({ message, busy, isLast }: { message: ChatMessage; busy?: boolean; isLast?: boolean }) {
  const isUser = message.role === 'user';
  if (isUser) {
    return (
      <div
        style={{
          padding: 'var(--space-2) var(--space-4)',
          borderRadius: 'var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg)',
          background: 'var(--accent)',
          color: 'var(--accent-fg)',
          border: '1px solid var(--accent)',
          fontSize: 'var(--text-chat)', lineHeight: 'var(--leading-chat)', wordBreak: 'break-word',
          boxShadow: 'var(--shadow-xs)',
        }}
      >
        <span style={{ whiteSpace: 'pre-wrap' }}>{message.content || (busy && isLast ? 'thinking…' : '')}</span>
      </div>
    );
  }
  // Assistant renders as flat article text — no bubble chrome, full reading width.
  return (
    <div style={{ padding: 'var(--space-1) 0', color: 'var(--fg-0)', minWidth: 0 }}>
      <Markdown content={message.content || (busy && isLast ? 'thinking…' : '')} />
      {/* Tool trace — collapsed by default to save vertical space */}
      {message.content && (
        <div style={{ marginTop: 'var(--space-2)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
          <Collapsible
            title="Tool trace"
            className="collapsible-bare"
            compact
            defaultOpen={false}
            meta={<span className="mono" style={{ padding: '1px 6px', background: message.gate?.ok ? 'var(--green-bg)' : 'var(--red-bg)', border: `1px solid ${message.gate?.ok ? 'var(--green-border)' : 'var(--red-border)'}`, borderRadius: 99, color: message.gate?.ok ? 'var(--green)' : 'var(--red)', fontSize: 'var(--text-2xs)' }}>{message.gate?.ok ? 'grounded' : 'unverified'}</span>}
          >
            <div style={{ padding: '0 var(--space-2) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className="mono" style={{ padding: '2px 6px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 99 }}>rg "{message.content.match(/`([^`]+)`/)?.[1] || 'symbol'}"</span>
                <span style={{ color: 'var(--fg-4)' }}>→</span>
                <span className="mono" style={{ padding: '2px 6px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 99 }}>write-gate {message.gate?.checked ?? 0} checked</span>
              </div>
              {message.gate && !message.gate.ok && message.gate.missing.length > 0 && (
                <div style={{ marginTop: 6, fontSize: 'var(--text-xs)' }}>
                  Missing: {message.gate.missing.map((sym) => (
                    <a key={sym} href="#" onClick={(e) => { e.preventDefault(); navigator.clipboard.writeText(sym); }} style={{ color: 'var(--accent)', textDecoration: 'underline', marginRight: 6 }}>{sym}</a>
                  ))}
                </div>
              )}
            </div>
          </Collapsible>
        </div>
      )}
    </div>
  );
}
