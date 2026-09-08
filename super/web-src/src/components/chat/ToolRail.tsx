import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChatMessage, ToolEvent } from '../../types';
import { Collapsible } from '../ui/Collapsible';
import { MediaAlbum } from './MediaAlbum';

export type ToolCallEntry = {
  key: string;
  name: string;
  call?: ToolEvent;
  result?: ToolEvent;
  msgIndex: number;
  ord: number;
};

/** Pair call→result events across messages; preserve chronological order. */
export function collectToolCalls(messages: ChatMessage[]): ToolCallEntry[] {
  const out: ToolCallEntry[] = [];
  let ord = 0;
  messages.forEach((m, msgIndex) => {
    const tools = m.tools || [];
    let i = 0;
    while (i < tools.length) {
      const t = tools[i];
      if (t.kind === 'call') {
        const next = tools[i + 1];
        const result = next && next.kind === 'result' && next.name === t.name ? next : undefined;
        out.push({
          key: `${msgIndex}-${ord}-${t.name}`,
          name: t.name,
          call: t,
          result,
          msgIndex,
          ord,
        });
        ord += 1;
        i += result ? 2 : 1;
      } else if (t.kind === 'result') {
        out.push({
          key: `${msgIndex}-${ord}-${t.name}-r`,
          name: t.name,
          result: t,
          msgIndex,
          ord,
        });
        ord += 1;
        i += 1;
      } else {
        i += 1;
      }
    }
  });
  return out;
}

function formatArgs(args: unknown): string {
  if (args == null) return '';
  if (typeof args === 'string') return args;
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

function ToolCallItem({
  entry, open, entering, onOpenChange,
}: {
  entry: ToolCallEntry;
  open: boolean;
  entering: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const pending = entry.call && !entry.result;
  const failed = entry.result && entry.result.ok === false;
  const status = pending ? 'running' : failed ? 'fail' : entry.result ? 'ok' : '—';

  return (
    <div className={entering ? 'tool-rail-enter' : undefined}>
      <Collapsible
        className={`collapsible-bare tool-rail-item${pending ? ' is-running' : ''}${failed ? ' is-fail' : ''}`}
        compact
        animated
        open={open}
        onOpenChange={onOpenChange}
        title={
          <span className="mono tool-rail-title" title={entry.name}>
            {entry.name}
          </span>
        }
        meta={
          <span
            className={`mono tool-rail-status status-${pending ? 'running' : failed ? 'fail' : 'ok'}`}
          >
            {status}
          </span>
        }
      >
        <div className="tool-rail-body">
          {entry.call?.arguments != null && (
            <div className="tool-rail-block">
              <div className="tool-rail-label mono">args</div>
              <pre className="tool-trace-body">{formatArgs(entry.call.arguments)}</pre>
            </div>
          )}
          {entry.result?.media && entry.result.media.length > 0 && (
            <div className="tool-rail-block tool-rail-result-enter">
              <div className="tool-rail-label mono">media</div>
              <MediaAlbum items={entry.result.media} compact />
            </div>
          )}
          {entry.result?.content != null && entry.result.content !== '' && (
            <div className="tool-rail-block tool-rail-result-enter">
              <div className="tool-rail-label mono">result</div>
              <pre className="tool-trace-body">
                {entry.result.content.slice(0, 1200)}
                {entry.result.content.length > 1200 ? '…' : ''}
              </pre>
            </div>
          )}
          {pending && (
            <div className="small muted tool-rail-running-hint">
              Running…
            </div>
          )}
        </div>
      </Collapsible>
    </div>
  );
}

export function ToolRail({ messages }: { messages: ChatMessage[]; busy?: boolean }) {
  const chronological = useMemo(() => collectToolCalls(messages), [messages]);
  const entries = useMemo(() => [...chronological].reverse(), [chronological]);
  const newestKey = entries[0]?.key ?? null;

  const [openKey, setOpenKey] = useState<string | null>(newestKey);
  const [entering, setEntering] = useState<Set<string>>(() => new Set());
  const knownRef = useRef<Set<string>>(new Set());
  const listRef = useRef<HTMLDivElement>(null);
  const enterTimers = useRef<Map<string, number>>(new Map());

  // Seed known keys on first non-empty list without animating history.
  useEffect(() => {
    if (!knownRef.current.size && entries.length) {
      knownRef.current = new Set(entries.map((e) => e.key));
      setOpenKey(newestKey);
    }
  }, [entries, newestKey]);

  // Animate only newly arrived calls; keep newest expanded.
  useEffect(() => {
    if (!newestKey) return;
    const known = knownRef.current;
    const fresh: string[] = [];
    for (const e of entries) {
      if (!known.has(e.key)) {
        known.add(e.key);
        fresh.push(e.key);
      }
    }
    if (!fresh.length) return;

    setOpenKey(newestKey);
    setEntering((prev) => {
      const next = new Set(prev);
      for (const k of fresh) next.add(k);
      return next;
    });
    for (const k of fresh) {
      const prev = enterTimers.current.get(k);
      if (prev) window.clearTimeout(prev);
      const t = window.setTimeout(() => {
        setEntering((prev) => {
          if (!prev.has(k)) return prev;
          const next = new Set(prev);
          next.delete(k);
          return next;
        });
        enterTimers.current.delete(k);
      }, 420);
      enterTimers.current.set(k, t);
    }
    const el = listRef.current;
    if (el) el.scrollTo({ top: 0, behavior: 'smooth' });
  }, [entries, newestKey]);

  useEffect(() => () => {
    for (const t of enterTimers.current.values()) window.clearTimeout(t);
  }, []);

  if (!entries.length) {
    return (
      <aside className="tool-rail" aria-label="Tool calls">
        <div className="tool-rail-head">
          <span>Tools</span>
          <span className="mono head-meta">{entries.length}</span>
        </div>
        <div className="tool-rail-empty muted small">
          Tool calls show up here as the agent works.
        </div>
      </aside>
    );
  }

  return (
    <aside className="tool-rail" aria-label="Tool calls">
      <div className="tool-rail-head">
        <span>Tools</span>
        <span className="mono head-meta tool-rail-count">{entries.length}</span>
      </div>
      <div className="tool-rail-list" ref={listRef}>
        {entries.map((e) => (
          <ToolCallItem
            key={e.key}
            entry={e}
            open={openKey === e.key}
            entering={entering.has(e.key)}
            onOpenChange={(next) => setOpenKey(next ? e.key : null)}
          />
        ))}
      </div>
    </aside>
  );
}
