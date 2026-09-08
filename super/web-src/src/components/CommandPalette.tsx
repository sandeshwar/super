import { useEffect, useId, useMemo, useRef, useState } from 'react';

type Item = { id: string; label: string; hint?: string; action: () => void };

export function CommandPalette({ items }: { items: Item[] }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === '/' && !open && !typing) {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === 'Escape' && open) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => {
    if (!open) { setQ(''); return; }
    const t = window.setTimeout(() => inputRef.current?.focus(), 30);
    setIdx(0);
    return () => window.clearTimeout(t);
  }, [open]);

  // Focus trap
  useEffect(() => {
    if (!open) return;
    const onTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', onTab);
    return () => window.removeEventListener('keydown', onTab);
  }, [open]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return items;
    return items.filter((i) => `${i.label} ${i.hint ?? ''}`.toLowerCase().includes(qq)).slice(0, 8);
  }, [items, q]);

  if (!open) return null;

  return (
    <div className="cmdk-overlay" role="dialog" aria-modal="true" aria-label="Commands" onClick={() => setOpen(false)}>
      <div className="cmdk" ref={panelRef} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder="Type a command — try chat, settings…"
          value={q}
          aria-controls={listId}
          aria-activedescendant={filtered[idx] ? `${listId}-${filtered[idx].id}` : undefined}
          onChange={(e) => { setQ(e.target.value); setIdx(0); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0))); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Enter') { e.preventDefault(); filtered[idx]?.action(); setOpen(false); }
          }}
        />
        <div className="cmdk-list" role="listbox" id={listId}>
          {filtered.map((it, i) => (
            <div
              key={it.id}
              id={`${listId}-${it.id}`}
              role="option"
              aria-selected={i === idx}
              className="cmdk-item"
              onMouseEnter={() => setIdx(i)}
              onClick={() => { it.action(); setOpen(false); }}
            >
              <span style={{ flex: 1 }}>{it.label}</span>
              {it.hint && <span className="mono small muted" style={{ fontSize: 'var(--text-xs)' }}>{it.hint}</span>}
            </div>
          ))}
          {filtered.length === 0 && <div className="small muted" style={{ padding: 'var(--space-3)', textAlign: 'center' }}>No matching commands</div>}
        </div>
        <div className="small muted" style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border)', display: 'flex', gap: 'var(--space-3)' }}>
          <span className="mono">↑↓ move</span><span className="mono">↵ pick</span><span className="mono">⎋ close</span><span className="mono" style={{ marginLeft: 'auto' }}>⌘K</span>
        </div>
      </div>
    </div>
  );
}
