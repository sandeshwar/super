import type { ApprovalRequest, ChatBlock, ChatMessage, ChildSpan, MediaPart } from '../../types';
import { Collapsible } from '../ui/Collapsible';
import { Markdown } from '../Markdown';
import { ApprovalCards } from './ApprovalCard';
import { MediaAlbum, mergeMedia } from './MediaAlbum';
import { ThinkingCard, normalizeThoughts } from './ThinkingCard';

function ChildAgentStrip({ children: kids, live }: { children: ChildSpan[]; live?: boolean }) {
  if (!kids.length) return null;
  return (
    <div className="child-agent-strip" aria-live={live ? 'polite' : undefined}>
      {kids.map((c) => (
        <div key={c.span_id} className={`child-agent-line status-${c.status}`}>
          <span className={`child-agent-dot status-${c.status}`} aria-hidden />
          <span className="mono child-agent-role">{c.role || 'worker'}</span>
          <span className="child-agent-summary" title={c.goal || c.summary}>{c.summary}</span>
        </div>
      ))}
    </div>
  );
}

function collectMedia(message: ChatMessage) {
  const fromBlocks = (message.blocks || [])
    .filter((b): b is Extract<ChatBlock, { kind: 'media' }> => b.kind === 'media')
    .flatMap((b) => b.media || []);
  const fromTools = (message.tools || [])
    .filter((t) => t.kind === 'result' && t.media?.length)
    .flatMap((t) => t.media || []);
  return mergeMedia(message.media, fromBlocks, fromTools);
}

/** Build interleaved timeline from blocks, or fall back to thoughts-then-content. */
function timelineBlocks(message: ChatMessage): ChatBlock[] {
  if (Array.isArray(message.blocks) && message.blocks.length) {
    return message.blocks.filter((b) => {
      if (!b || !b.kind) return false;
      if (b.kind === 'thinking' || b.kind === 'text') return !!(b.text || '').trim();
      if (b.kind === 'media') return !!(b.media && b.media.length);
      return false;
    });
  }
  const out: ChatBlock[] = [];
  for (const t of normalizeThoughts(message)) {
    out.push({ kind: 'thinking', text: t });
  }
  if ((message.content || '').trim()) {
    out.push({ kind: 'text', text: message.content });
  }
  const album = collectMedia(message);
  if (album.length) {
    out.push({ kind: 'media', media: album });
  }
  return out;
}

function thoughtIndex(blocks: ChatBlock[], at: number): { index: number; total: number } {
  const total = blocks.filter((b) => b.kind === 'thinking').length;
  let index = 0;
  for (let i = 0; i <= at; i++) {
    if (blocks[i]?.kind === 'thinking') index += 1;
  }
  return { index, total };
}

export function MessageBubble({
  message, busy, isLast, onApprovalsChange,
}: {
  message: ChatMessage;
  busy?: boolean;
  isLast?: boolean;
  onApprovalsChange?: (approvals: ApprovalRequest[]) => void;
}) {
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
  const kids = message.children || [];
  const approvals = message.approvals || [];
  const streaming = !!(busy && isLast);
  const blocks = timelineBlocks(message);
  const livePending = streaming && message.thinkingLive && !blocks.some((b) => b.kind === 'thinking');
  // Avoid duplicating album if already inlined as media blocks.
  const hasInlineMedia = blocks.some((b) => b.kind === 'media');
  const looseAlbum: MediaPart[] = hasInlineMedia ? [] : collectMedia(message);

  const tools = message.tools || [];
  const lastTool = tools[tools.length - 1];
  const toolRunning = !!(streaming && lastTool && lastTool.kind === 'call');
  const streamStatus = streaming
    ? (message.thinkingLive || livePending
      ? 'Thinking…'
      : toolRunning
        ? `Running ${lastTool.name}…`
        : (message.content || '').trim()
          ? 'Writing…'
          : 'Waiting…')
    : null;

  return (
    <div style={{ padding: 'var(--space-1) 0', color: 'var(--fg-0)', minWidth: 0 }}>
      {!!kids.length && <ChildAgentStrip children={kids} live={streaming} />}
      {!!approvals.length && (
        <ApprovalCards
          approvals={approvals}
          onResolved={onApprovalsChange}
        />
      )}
      <div className="chat-timeline">
        {blocks.map((b, i) => {
          if (b.kind === 'thinking') {
            const { index, total } = thoughtIndex(blocks, i);
            const isLastThought = !blocks.slice(i + 1).some((x) => x.kind === 'thinking');
            const stepLive = !!(streaming && isLastThought && message.thinkingLive);
            return (
              <ThinkingCard
                key={`th-${i}-${b.step ?? index}`}
                thinking={b.text}
                streaming={streaming}
                hasOutput={!stepLive}
                index={index}
                total={total}
              />
            );
          }
          if (b.kind === 'text') {
            return (
              <div key={`tx-${i}-${b.step ?? 0}`} className="chat-timeline-text">
                <Markdown content={b.text} />
              </div>
            );
          }
          if (b.kind === 'media') {
            return <MediaAlbum key={`md-${i}-${b.step ?? 0}`} items={b.media} />;
          }
          return null;
        })}
        {livePending && (
          <ThinkingCard thinking="" streaming hasOutput={false} index={1} total={1} />
        )}
        {!!looseAlbum.length && <MediaAlbum items={looseAlbum} />}
        {streamStatus && (
          <div className="chat-stream-status mono" role="status" aria-live="polite">
            <span className="dot" style={{ background: 'var(--yellow)' }} aria-hidden />
            {streamStatus}
          </div>
        )}
      </div>
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
