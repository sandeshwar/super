import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { useToolPrefs } from '../../lib/toolPrefs';

const SLASH_COMMANDS = [
  { cmd: '/add-task', desc: 'Add a task' },
  { cmd: '/spec-pin', desc: 'Pin acceptance checks for a task' },
  { cmd: '/prove', desc: 'Attach proof to a task' },
  { cmd: '/clear', desc: 'Clear this chat' },
  { cmd: '/export', desc: 'Export this chat' },
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
  mentionPaths: string[];
  setMentionIndex: (fn: (i: number) => number) => void;
  onClosePopovers: () => void;
  onInput: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onShare: () => void;
  onFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
};

function autosize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
}

export function ChatDock({
  input, busy, messagesLen, cost, showSlash, slashFilter, showMention, mentionFilter,
  mentionIndex, mentionPaths, setMentionIndex, onClosePopovers, onInput, onSend, onStop, onShare, onFile, inputRef,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  const prefs = useToolPrefs();
  const slashItems = useMemo(
    () => SLASH_COMMANDS.filter((c) => !slashFilter || c.cmd.includes(slashFilter) || c.desc.toLowerCase().includes(slashFilter)),
    [slashFilter],
  );
  const mentionItems = useMemo(() => {
    const pool = mentionPaths.length
      ? mentionPaths
      : ['super/harness.py', 'super/gates.py', 'super/llm.py', 'super/config.py', 'super/server.py'];
    return pool
      .filter((p) => !mentionFilter || p.toLowerCase().includes(mentionFilter))
      .slice(0, 8);
  }, [mentionFilter, mentionPaths]);

  useEffect(() => { autosize(inputRef.current); }, [input, inputRef]);

  const pickSlash = (cmd: string) => {
    onInput(cmd + ' ');
    onClosePopovers();
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const slashOpen = prefs.slashCommands && showSlash && slashItems.length > 0;
  const mentionOpen = prefs.fileMentions && showMention && mentionItems.length > 0;

  return (
    <div className="chat-dock">
      {slashOpen && (
        <Card className="chat-dock-pop" role="listbox" aria-label="Commands">
          {slashItems.map((c, i) => (
            <button
              key={c.cmd}
              type="button"
              role="option"
              aria-selected={i === slashIndex}
              onClick={() => pickSlash(c.cmd)}
              className="chat-dock-option"
              style={{ background: i === slashIndex ? 'var(--accent-soft)' : 'transparent' }}
            >
              <span className="mono" style={{ color: 'var(--accent)', fontWeight: 600 }}>{c.cmd}</span>
              <span className="small muted">{c.desc}</span>
            </button>
          ))}
        </Card>
      )}
      {mentionOpen && (
        <Card className="chat-dock-pop" role="listbox" aria-label="Files">
          {mentionItems.map((p, idx) => (
            <button
              key={p}
              type="button"
              role="option"
              aria-selected={idx === mentionIndex}
              onClick={() => { onInput(input.replace(/@[^ ]*$/, `@${p} `)); onClosePopovers(); }}
              className="chat-dock-option mono small"
              style={{ background: idx === mentionIndex ? 'var(--accent-soft)' : 'transparent' }}
            >
              {p}
            </button>
          ))}
        </Card>
      )}

      <div className="chat-dock-row">
        <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={onFile} accept=".txt,.md,.py,.js,.ts,.json" />
        {prefs.attachFiles && (
          <Button
            size="icon-sm"
            variant="ghost"
            className="chat-dock-attach"
            onClick={() => fileRef.current?.click()}
            title="Attach file"
            aria-label="Attach file"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3.5a2 2 0 00-2 2v5a2 2 0 002 2 2 2 0 002-2v-5.5a1 1 0 00-1-1 1 1 0 00-1 1v5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          </Button>
        )}
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => { onInput(e.target.value); setSlashIndex(0); }}
          onKeyDown={(e) => {
            if (slashOpen) {
              if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIndex((i) => Math.min(i + 1, slashItems.length - 1)); return; }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSlashIndex((i) => Math.max(i - 1, 0)); return; }
              if (e.key === 'Tab' || (e.key === 'Enter' && !e.metaKey && !e.ctrlKey)) {
                e.preventDefault();
                pickSlash(slashItems[slashIndex]?.cmd ?? slashItems[0].cmd);
                return;
              }
            }
            if (mentionOpen && mentionItems.length) {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setMentionIndex((i) => (e.key === 'ArrowDown' ? Math.min(i + 1, mentionItems.length - 1) : Math.max(i - 1, 0)));
                return;
              }
              if (e.key === 'Tab' || (e.key === 'Enter' && !e.metaKey && !e.ctrlKey)) {
                e.preventDefault();
                const p = mentionItems[mentionIndex] ?? mentionItems[0];
                onInput(input.replace(/@[^ ]*$/, `@${p} `));
                onClosePopovers();
                return;
              }
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
            if (e.key === 'Escape') onClosePopovers();
          }}
          placeholder={prefs.slashCommands || prefs.fileMentions
            ? `Ask about the project…${prefs.slashCommands ? '  (/ commands' : ''}${prefs.slashCommands && prefs.fileMentions ? ',' : ''}${prefs.fileMentions ? (prefs.slashCommands ? ' @ files)' : '  (@ files)') : prefs.slashCommands ? ')' : ''}`
            : 'Ask about the project…'}
          rows={1}
          aria-label="Message"
        />
        {busy ? (
          <Button variant="ghost" className="chat-dock-send" onClick={onStop} aria-label="Stop">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><rect x="4" y="4" width="8" height="8" rx="1" fill="currentColor"/></svg>
            Stop
          </Button>
        ) : (
          <Button variant="primary" className="chat-dock-send" onClick={onSend} disabled={!input.trim()}>
            Send
          </Button>
        )}
      </div>

      <div className="chat-dock-meta panel-foot">
        {prefs.showShortcuts ? (
          <span className="chat-dock-hint mono">Enter send · Shift+Enter newline{prefs.slashCommands ? ' · / commands' : ''}{prefs.fileMentions ? ' · @ files' : ''}</span>
        ) : <span />}
        <span className="chat-dock-meta-right">
          <Button size="sm" variant="ghost" onClick={onShare} title="Export chat" disabled={!messagesLen}>Export</Button>
          <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>{messagesLen} msgs</Badge>
          {cost && <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>~{cost.total} tok</Badge>}
        </span>
      </div>
    </div>
  );
}
