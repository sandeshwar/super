import { useRef } from 'react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Collapsible } from '../ui/Collapsible';

const SLASH_COMMANDS = [
  { cmd: '/add-task', desc: 'Add task: /add-task Title --done "check"' },
  { cmd: '/spec-pin', desc: 'Pin spec: /spec-pin <id> <acceptance>' },
  { cmd: '/prove', desc: 'Prove task: /prove <id> <proof>' },
  { cmd: '/clear', desc: 'Clear chat' },
  { cmd: '/export', desc: 'Export chat as md/json' },
];

type Props = {
  input: string;
  busy: boolean;
  messagesLen: number;
  cost: { total: number } | null;
  showSlash: boolean;
  slashFilter: string;
  showMention: boolean;
  mentionFilter: string;
  mentionIndex: number;
  setMentionIndex: (fn: (i: number) => number) => void;
  onClosePopovers: () => void;
  onInput: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onShare: () => void;
  onFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
};

export function ChatDock({ input, busy, messagesLen, cost, showSlash, slashFilter, showMention, mentionFilter, mentionIndex, setMentionIndex, onClosePopovers, onInput, onSend, onStop, onShare, onFile, inputRef }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="chat-dock" style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border)', background: 'var(--bg-1)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      {showSlash && (
        <Card style={{ padding: 'var(--space-2)', position: 'relative', marginBottom: 'var(--space-1)' }}>
          {SLASH_COMMANDS.filter((c) => !slashFilter || c.cmd.includes(slashFilter) || c.desc.toLowerCase().includes(slashFilter)).map((c) => (
            <button key={c.cmd} onClick={() => { onInput(c.cmd + ' '); setTimeout(()=> inputRef.current?.focus(), 0); }} style={{ display: 'flex', justifyContent: 'space-between', width: '100%', padding: '6px 8px', borderRadius: 'var(--radius-xs)', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left' }}>
              <span className="mono" style={{ color: 'var(--accent)', fontWeight: 600 }}>{c.cmd}</span><span className="small muted">{c.desc}</span>
            </button>
          ))}
        </Card>
      )}
      {showMention && (
        <Card style={{ padding: 'var(--space-2)' }}>
          {['super/harness.py', 'super/gates.py', 'super/llm.py', 'super/config.py', 'super/memory.py'].filter((p) => !mentionFilter || p.toLowerCase().includes(mentionFilter)).slice(0, 5).map((p, idx) => (
            <button key={p} onClick={() => { onInput(input.replace(/@[^ ]*$/, `@${p} `)); }} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', borderRadius: 'var(--radius-xs)', background: idx === mentionIndex ? 'var(--accent-soft)' : 'transparent', border: 'none', cursor: 'pointer' }} className="mono small">{p}</button>
          ))}
        </Card>
      )}
      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-end' }}>
        <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={onFile} accept=".txt,.md,.py,.js,.ts,.json" />
        <Button size="sm" variant="ghost" onClick={() => fileRef.current?.click()} title="Attach file" aria-label="Attach file">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3.5a2 2 0 00-2 2v5a2 2 0 002 2 2 2 0 002-2v-5.5a1 1 0 00-1-1 1 1 0 00-1 1v5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
        </Button>
        <div style={{ flex: 1, position: 'relative' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
              if (e.key === 'Escape') { onClosePopovers(); }
              if (showMention && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
                e.preventDefault();
                setMentionIndex((i) => (e.key === 'ArrowDown' ? Math.min(i + 1, 4) : Math.max(i - 1, 0)));
              }
            }}
            placeholder="Ask about the repo…  (/ for commands, @ for files)"
            rows={1}
            style={{
              width: '100%', resize: 'none', minHeight: 36, maxHeight: 120,
              padding: '6px var(--space-2)', borderRadius: 'var(--radius)', background: 'var(--bg-2)', border: '1px solid var(--border)',
              color: 'var(--fg-0)', font: '400 var(--text-sm) var(--font-sans)', outline: 'none',
              lineHeight: 'var(--leading-normal)',
            }}
            aria-label="Message"
          />
          <div style={{ position: 'absolute', right: 8, bottom: 8, display: 'flex', gap: 4 }}>
            <span className="mono small muted" style={{ fontSize: 'var(--text-2xs)', opacity: 0.6 }}>/</span>
            <span className="mono small muted" style={{ fontSize: 'var(--text-2xs)', opacity: 0.6 }}>@</span>
          </div>
        </div>
        {busy ? (
          <Button variant="ghost" onClick={onStop} style={{ height: 36, padding: '0 var(--space-2)', borderRadius: 'var(--radius)' }} aria-label="Stop generation">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor"/></svg>
            Stop
          </Button>
        ) : (
          <Button variant="primary" onClick={onSend} disabled={!input.trim()} style={{ height: 36, padding: '0 var(--space-3)', borderRadius: 'var(--radius)' }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M13.5 2.5L2.8 7.2l4.1 1.6 1.6 4.1 5-10.4z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>
            Send
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onShare} title="Export chat" disabled={!messagesLen}>share</Button>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--fg-4)' }}>
        <Collapsible title="Shortcuts" className="collapsible-bare" compact defaultOpen={false}>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap', paddingBottom: 2 }}>
            <span className="mono">⌘+Enter to send · / commands · @ files</span>
            <span style={{ width: 3, height: 3, borderRadius: 'var(--radius-full)', background: 'var(--fg-4)' }} aria-hidden />
            <span>Backticked <code style={{ fontSize: 'var(--text-xs)' }}>symbols</code> are ground-checked</span>
          </div>
        </Collapsible>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>{messagesLen} msgs</Badge>
          {busy && <Badge variant="accent" style={{ fontSize: 'var(--text-2xs)' }}>streaming</Badge>}
          {cost && <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>~{cost.total} tok</Badge>}
        </span>
      </div>
    </div>
  );
}
