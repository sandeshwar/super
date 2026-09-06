import { useEffect, useMemo, useState } from 'react';
import type { TaskNode } from '../types';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHead } from './ui/Card';
import { Collapsible } from './ui/Collapsible';
import { Input, Select } from './ui/Input';
import { DagGraph } from './Graph/DagGraph';
import { userMessage } from '../lib/errors';

// Single responsibility: status badge
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, 'proven' | 'waiting' | 'doing' | 'blocked' | 'neutral'> =
    { proven: 'proven', waiting: 'waiting', doing: 'doing', blocked: 'blocked' };
  const v = map[status] ?? 'neutral';
  return <Badge variant={v}><span className="badge-dot" aria-hidden />{status}</Badge>;
}

type Filter = 'all' | TaskNode['status'];

// ── Subcomponents (SRP) ──
function Toolbar({
  q, setQ, f, setF, sort, setSort, counts, total, filtered,
}: {
  q: string; setQ: (v: string) => void; f: Filter; setF: (v: Filter) => void;
  sort: 'id' | 'status'; setSort: (v: 'id' | 'status') => void;
  counts: Record<string, number>; total: number; filtered: number;
}) {
  return (
    <Card style={{ padding: 'var(--space-2)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}>
      <div style={{ display: 'flex', gap: 'var(--space-1)', alignItems: 'center', flexWrap: 'wrap' }}>
        {(['all', 'waiting', 'doing', 'proven', 'blocked'] as Filter[]).map((k) => (
          <Button key={k} size="sm" variant={f === k ? 'primary' : 'default'} onClick={() => setF(k)} style={f === k ? {} : { background: 'var(--bg-1)' }}>
            {k} <span className="mono" style={{ opacity: .7, marginLeft: 4 }}>{(counts as Record<string, number>)[k] ?? 0}</span>
          </Button>
        ))}
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative' }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-4)' }} aria-hidden><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2"/><path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by title, why, done…" style={{ paddingLeft: 28, width: 260 }} aria-label="Filter tasks" />
        </div>
        <Select value={sort} onChange={(e) => setSort(e.target.value as 'id' | 'status')} style={{ width: 120 }} aria-label="Sort">
          <option value="id">Sort: ID</option>
          <option value="status">Sort: Status</option>
        </Select>
        <span className="mono small muted" style={{ padding: 'var(--space-1) var(--space-2)', background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>{filtered} / {total}</span>
      </div>
    </Card>
  );
}

export default function TreeView({ tasks, gates }: { tasks: TaskNode[]; gates?: Record<string, { pass: number; reject: number }> }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [f, setF] = useState<Filter>('all');
  const [sort, setSort] = useState<'id' | 'status'>('id');
  const [copyError, setCopyError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    let r = [...tasks];
    if (q.trim()) {
      const qq = q.toLowerCase();
      r = r.filter((t) => `${t.id} ${t.title} ${t.why} ${t.done}`.toLowerCase().includes(qq));
    }
    if (f !== 'all') r = r.filter((t) => t.status === f);
    r.sort((a, b) => (sort === 'status' ? a.status.localeCompare(b.status) || a.id.localeCompare(b.id) : a.id.localeCompare(b.id)));
    return r;
  }, [tasks, q, f, sort]);

  const sel = useMemo(() => filtered.find((t) => t.id === selected) ?? tasks.find((t) => t.id === selected) ?? filtered[0] ?? tasks[0] ?? null, [filtered, tasks, selected]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: tasks.length };
    for (const t of tasks) c[t.status] = (c[t.status] || 0) + 1;
    return c;
  }, [tasks]);

  useEffect(() => { if (!selected && filtered[0]) setSelected(filtered[0].id); }, [filtered, selected]);

  useEffect(() => {
    const h = (e: Event) => setQ((e as CustomEvent).detail || '');
    const nav = (e: Event) => {
      const dir = (e as CustomEvent).detail as string;
      if (!filtered.length) return;
      const idx = filtered.findIndex((t) => t.id === selected);
      if (dir === 'next') setSelected(filtered[Math.min(idx + 1, filtered.length - 1)]?.id ?? filtered[0].id);
      if (dir === 'prev') setSelected(filtered[Math.max(idx - 1, 0)]?.id ?? filtered[0].id);
    };
    window.addEventListener('super-search' as unknown as string, h as EventListener);
    window.addEventListener('super-nav' as unknown as string, nav as EventListener);
    return () => {
      window.removeEventListener('super-search' as unknown as string, h as EventListener);
      window.removeEventListener('super-nav' as unknown as string, nav as EventListener);
    };
  }, [filtered, selected]);

  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setCopyError(null); }
    catch (e) { setCopyError(userMessage(e)); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <Toolbar q={q} setQ={setQ} f={f} setF={setF} sort={sort} setSort={setSort} counts={counts} total={tasks.length} filtered={filtered.length} />
      <Collapsible title="Dependency graph" storageKey="tree-dag" meta={<span className="mono">{tasks.length} nodes · drag to pan · ⌘+wheel zoom</span>} compact>
        <DagGraph tasks={tasks} selected={selected} onSelect={setSelected} bare />
      </Collapsible>

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 0.85fr', gap: 'var(--space-3)' }}>
        {/* List */}
        <Card style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <CardHead>
            <h3><svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M2.5 5.5h11M2.5 8h11M2.5 10.5h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg> Tasks</h3>
            <span className="head-meta mono">{filtered.length} shown</span>
          </CardHead>

          <div style={{ flex: 1, overflow: 'auto', background: 'var(--bg-1)' }}>
            {filtered.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden><svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 8h5M8 5.5v5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg></div>
                <h4>No tasks match</h4>
                <p>Try a different filter or add a task:<br /><code>python3 -m super.cli task-add "Title" --done "check" --why "reason"</code></p>
                <Button size="sm" onClick={() => { setQ(''); setF('all'); }}>Clear filters</Button>
              </div>
            ) : (
              <div style={{ padding: 'var(--space-1)', display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
                {filtered.map((t) => {
                  const isActive = sel?.id === t.id;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setSelected(t.id)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 'var(--space-2)', width: '100%', textAlign: 'left',
                        padding: 'var(--space-2)', borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                        background: isActive ? 'var(--accent-soft)' : 'var(--bg-2)',
                        border: `1px solid ${isActive ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
                        transition: 'background var(--ease), border-color var(--ease)',
                      }}
                    >
                      <span className="mono" style={{
                        minWidth: 34, height: 24, display: 'grid', placeItems: 'center', borderRadius: 'var(--radius-xs)',
                        background: isActive ? 'var(--accent)' : 'var(--bg-3)', color: isActive ? 'var(--accent-fg)' : 'var(--fg-2)',
                        border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`, fontSize: 'var(--text-xs)', fontWeight: 700,
                      }}>{t.id}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ fontWeight: isActive ? 600 : 500, fontSize: 'var(--text-base)', color: isActive ? 'var(--fg-0)' : 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>{t.title}</span>
                        <span className="small muted" style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', marginTop: 2, fontSize: 'var(--text-xs)' }}>
                          <span className="truncate" style={{ maxWidth: 180 }}>{t.needs.length ? `${t.needs.length} deps` : 'no deps'} · {t.parent ? `parent ${t.parent}` : 'root'}</span>
                          <span style={{ width: 3, height: 3, borderRadius: 'var(--radius-full)', background: 'var(--fg-4)' }} aria-hidden />
                          <span className="truncate" style={{ maxWidth: 140 }}>{t.why || '—'}</span>
                        </span>
                      </span>
                      <StatusBadge status={t.status} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-2)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', flexWrap: 'wrap' }}>
            <span className="mono">{tasks.filter((t) => t.status === 'proven').length}/{tasks.length} proven</span>
            <span aria-hidden>·</span>
            <span className="mono">gate log: {gates ? Object.entries(gates).slice(0,3).map(([k,s])=> `${k} ${s.pass}:${s.reject}`).join(' · ') || '—' : '—'}</span>
            <span aria-hidden>·</span>
            <span className="mono">issues: {gates ? Object.values(gates).reduce((acc,g)=>acc+g.reject,0) : 0}</span>
            <Badge variant="neutral" style={{ marginLeft: 'auto', fontSize: 'var(--text-2xs)' }}>DAG leaf model</Badge>
          </div>
        </Card>

        {/* Detail */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', overflow: 'auto' }}>
          {sel ? (
            <>
              <Card style={{ overflow: 'hidden' }}>
                <div style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', marginBottom: 'var(--space-1)' }}>
                        <Badge variant="neutral" style={{ fontSize: 'var(--text-xs)' }}># {sel.id}</Badge>
                        <StatusBadge status={sel.status} />
                        {sel.parent && <Badge variant="neutral">parent {sel.parent}</Badge>}
                      </div>
                      <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: 'var(--tracking-tight)', color: 'var(--fg-0)', lineHeight: 'var(--leading-tight)' }}>{sel.title}</h3>
                    </div>
                    <Badge variant="accent" style={{ fontSize: 'var(--text-xs)' }}>{sel.needs.length} deps</Badge>
                  </div>

                  <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
                    {[
                      { k: 'WHY', v: sel.why || '—' },
                      { k: 'DONE LOOKS LIKE', v: sel.done || '—' },
                      { k: 'NEEDS', v: sel.needs.length ? sel.needs.join(', ') : 'nothing · leaf ready', mono: true },
                      { k: 'BLOCKS', v: sel.blocks?.length ? sel.blocks.join(', ') : '—', mono: true },
                      { k: 'FILES', v: sel.files?.length ? sel.files.join(', ') : '—', mono: true },
                      { k: 'PROOF', v: sel.proof || '(empty — not proven)', mono: true, empty: !sel.proof },
                    ].map(({ k, v, mono, empty }) => (
                      <div key={k} style={{ padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)' }}>
                        <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-1)' }}>{k}</div>
                        <div style={{ fontSize: 'var(--text-base)', color: empty ? 'var(--fg-3)' : 'var(--fg-1)', fontFamily: mono ? 'var(--font-mono)' : undefined, fontStyle: empty ? 'italic' : undefined, lineHeight: 'var(--leading-normal)', wordBreak: 'break-word' }}>{v}</div>
                      </div>
                    ))}
                  </div>
                  {copyError && <div className="alert alert--error" style={{ fontSize: 'var(--text-sm)' }}>{copyError}</div>}
                </div>

                <div style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-1)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  <span className="mono small muted" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: sel.status === 'proven' ? 'var(--green)' : sel.status === 'blocked' ? 'var(--red)' : 'var(--yellow)', display: 'inline-block' }} aria-hidden />{sel.status}</span>
                  <span style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-2)' }}>
                    <Button size="sm" variant="default" onClick={() => void copy(sel.id)}>copy id</Button>
                    <Button size="sm" variant="primary" onClick={() => void copy(sel.title)}>copy title</Button>
                  </span>
                </div>
              </Card>

              <Collapsible title="Dependency trace" storageKey="tree-trace" defaultOpen={false} compact meta={<span className="mono">{sel.needs.length ? `${sel.needs.length} deps` : 'leaf'} → #{sel.id}</span>}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {(sel.needs.length ? sel.needs : ['∅ leaf']).map((n) => (
                    <Badge key={n} variant={n === '∅ leaf' ? 'proven' : 'neutral'} style={{ fontSize: 'var(--text-xs)' }}>{n}</Badge>
                  ))}
                  <span style={{ color: 'var(--fg-4)' }} aria-hidden>→</span>
                  <Badge variant="accent" style={{ fontSize: 'var(--text-xs)' }}>#{sel.id}</Badge>
                </div>
                <div className="divider" />
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg-3)', lineHeight: 'var(--leading-normal)' }}>
                  Leaf holds one job. The harness holds the forest — model sees only this card + compiled memory + repo overview.
                </div>
              </Collapsible>
            </>
          ) : (
            <Card style={{ padding: 'var(--space-10)', textAlign: 'center', color: 'var(--fg-3)' }}>
              <div className="empty"><div className="empty-icon" aria-hidden><svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M8 6v3M8 11h.01" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2"/></svg></div><p>Select a task to inspect provenance</p></div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
