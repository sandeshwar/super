import { useEffect, useMemo, useRef, useState } from 'react';

type Item = { id: string; label: string; hint?: string; action: () => void };

export function CommandPalette({ items }: { items: Item[] }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen((v) => !v); }
      if (e.key === '/' && !open && (e.target as HTMLElement)?.tagName !== 'INPUT' && (e.target as HTMLElement)?.tagName !== 'TEXTAREA') { e.preventDefault(); setOpen(true); }
      if (e.key === 'Escape' && open) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => { if (open) { setTimeout(() => inputRef.current?.focus(), 30); setIdx(0); } else setQ(''); }, [open]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return items;
    return items.filter((i) => `${i.label} ${i.hint ?? ''}`.toLowerCase().includes(qq)).slice(0, 8);
  }, [items, q]);

  if (!open) return null;

  return (
    <div className="cmdk-overlay" role="dialog" aria-modal="true" aria-label="Command palette" onClick={() => setOpen(false)}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder="Type a command — try 'chat', 'tree', 'approve'..."
          value={q}
          onChange={(e) => { setQ(e.target.value); setIdx(0); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, filtered.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Enter') { e.preventDefault(); filtered[idx]?.action(); setOpen(false); }
          }}
        />
        <div className="cmdk-list" role="listbox">
          {filtered.map((it, i) => (
            <div
              key={it.id}
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
          {filtered.length === 0 && <div className="small muted" style={{ padding: 'var(--space-3)', textAlign: 'center' }}>No commands match</div>}
        </div>
        <div className="small muted" style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border)', display: 'flex', gap: 'var(--space-3)' }}>
          <span className="mono">↑↓ navigate</span><span className="mono">↵ select</span><span className="mono">⎋ close</span><span className="mono" style={{ marginLeft: 'auto' }}>⌘K</span>
        </div>
      </div>
    </div>
  );
}
