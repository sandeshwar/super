import type { ChatMessage, ToolEvent } from '../../types';
import { Collapsible } from '../ui/Collapsible';
import { Markdown } from '../Markdown';

function ToolTrace({ tools }: { tools: ToolEvent[] }) {
  if (!tools.length) return null;
  const calls = tools.filter((t) => t.kind === 'call').length;
  return (
    <div style={{ marginBottom: 'var(--space-2)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
      <Collapsible
        title="Tools used"
        className="collapsible-bare"
        compact
        defaultOpen
        meta={
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>
            {calls} call{calls !== 1 ? 's' : ''}
          </span>
        }
      >
        <div className="tool-trace" style={{ padding: '0 var(--space-2) var(--space-2)' }}>
          {tools.map((t, i) => (
            <div key={`${t.kind}-${t.name}-${i}`} className={`tool-trace-row ${t.kind}`}>
              <span className="mono tool-trace-kind">{t.kind === 'call' ? '→' : '←'}</span>
              <span className="mono tool-trace-name">{t.name}</span>
              {t.kind === 'result' && (
                <span className="mono" style={{ color: t.ok ? 'var(--green)' : 'var(--red)' }}>{t.ok ? 'ok' : 'fail'}</span>
              )}
              {t.kind === 'call' && t.arguments != null && (
                <pre className="tool-trace-body">{typeof t.arguments === 'string' ? t.arguments : JSON.stringify(t.arguments, null, 2)}</pre>
              )}
              {t.kind === 'result' && t.content && (
                <pre className="tool-trace-body">{t.content.slice(0, 600)}{t.content.length > 600 ? '…' : ''}</pre>
              )}
            </div>
          ))}
        </div>
      </Collapsible>
    </div>
  );
}

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
        <span style={{ whiteSpace: 'pre-wrap' }}>{message.content || (busy && isLast ? '…' : '')}</span>
      </div>
    );
  }
  const tools = message.tools || [];
  return (
    <div style={{ padding: 'var(--space-1) 0', color: 'var(--fg-0)', minWidth: 0 }}>
      {!!tools.length && <ToolTrace tools={tools} />}
      <Markdown content={message.content || (busy && isLast ? (tools.length ? 'Working…' : 'Thinking…') : '')} />
      {message.gate && message.gate.checked > 0 && (
        <div style={{ marginTop: 'var(--space-2)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
          <Collapsible
            title="Symbol check"
            className="collapsible-bare"
            compact
            defaultOpen={!message.gate.ok}
            meta={
              <span
                className="mono"
                style={{
                  padding: '1px 6px',
                  background: message.gate.ok ? 'var(--green-bg)' : 'var(--red-bg)',
                  border: `1px solid ${message.gate.ok ? 'var(--green-border)' : 'var(--red-border)'}`,
                  borderRadius: 99,
                  color: message.gate.ok ? 'var(--green)' : 'var(--red)',
                  fontSize: 'var(--text-2xs)',
                }}
              >
                {message.gate.ok ? 'ok' : 'issues'}
              </span>
            }
          >
            <div style={{ padding: '0 var(--space-2) var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
              <div>Checked {message.gate.checked} symbol{message.gate.checked !== 1 ? 's' : ''} against the repo.</div>
              {!message.gate.ok && message.gate.missing.length > 0 && (
                <div style={{ marginTop: 6 }}>
                  Not found:{' '}
                  {message.gate.missing.map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => { void navigator.clipboard.writeText(sym); }}
                      style={{ color: 'var(--accent)', textDecoration: 'underline', marginRight: 6, background: 'none', border: 'none', cursor: 'pointer', font: 'inherit' }}
                    >
                      {sym}
                    </button>
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
