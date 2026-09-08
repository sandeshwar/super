import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode, type RefObject } from 'react';
import type { TaskNode } from '../types';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHead } from './ui/Card';
import { Collapsible } from './ui/Collapsible';
import { Input, Select } from './ui/Input';
import { DagGraph } from './Graph/DagGraph';
import { userMessage } from '../lib/errors';
import { statusLabel, FILTER_LABEL } from '../lib/labels';
import { navigate, type TreeFilter, type TreeSort } from '../lib/router';

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, 'proven' | 'waiting' | 'doing' | 'blocked' | 'neutral'> = {
    proven: 'proven',
    waiting: 'waiting',
    doing: 'doing',
    blocked: 'blocked',
  };
  const v = map[status] ?? 'neutral';
  return (
    <Badge variant={v}>
      <span className="badge-dot" aria-hidden />
      {statusLabel(status)}
    </Badge>
  );
}

type TreeRoutePatch = {
  taskId?: string | null;
  q?: string;
  status?: TreeFilter;
  sort?: TreeSort;
};

function parentKey(p: string | null | undefined): string | null {
  if (p == null || p === '') return null;
  return p;
}

function buildChildrenMap(tasks: TaskNode[]): Map<string | null, TaskNode[]> {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const kids = new Map<string | null, TaskNode[]>();
  for (const t of tasks) {
    let p = parentKey(t.parent);
    // Orphan → treat as root if parent missing from set
    if (p != null && !byId.has(p)) p = null;
    if (!kids.has(p)) kids.set(p, []);
    kids.get(p)!.push(t);
  }
  return kids;
}

function ancestorIds(taskId: string | null | undefined, byId: Map<string, TaskNode>): string[] {
  if (!taskId) return [];
  const out: string[] = [];
  let cur = byId.get(taskId);
  const seen = new Set<string>();
  while (cur) {
    const p = parentKey(cur.parent);
    if (!p || seen.has(p)) break;
    seen.add(p);
    out.push(p);
    cur = byId.get(p);
  }
  return out;
}

function sortTasks(list: TaskNode[], sort: TreeSort): TaskNode[] {
  const r = [...list];
  r.sort((a, b) =>
    sort === 'status'
      ? a.status.localeCompare(b.status) || a.id.localeCompare(b.id)
      : a.id.localeCompare(b.id),
  );
  return r;
}

function matchesQuery(t: TaskNode, q: string): boolean {
  if (!q.trim()) return true;
  const qq = q.toLowerCase();
  return `${t.id} ${t.title} ${t.why} ${t.done}`.toLowerCase().includes(qq);
}

function Toolbar({
  q,
  setQ,
  f,
  setF,
  sort,
  setSort,
  counts,
  total,
  filtered,
  inputRef,
}: {
  q: string;
  setQ: (v: string) => void;
  f: TreeFilter;
  setF: (v: TreeFilter) => void;
  sort: TreeSort;
  setSort: (v: TreeSort) => void;
  counts: Record<string, number>;
  total: number;
  filtered: number;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  const filters: TreeFilter[] = ['all', 'waiting', 'doing', 'proven', 'blocked'];
  return (
    <Card className="tree-toolbar">
      <div className="tree-filters">
        {filters.map((k) => (
          <Button
            key={k}
            size="sm"
            variant={f === k ? 'primary' : 'default'}
            onClick={() => setF(k)}
            style={f === k ? undefined : { background: 'var(--bg-1)' }}
          >
            {FILTER_LABEL[k] ?? k}{' '}
            <span className="mono count">{counts[k] ?? 0}</span>
          </Button>
        ))}
      </div>
      <div className="tree-toolbar-end">
        <div className="tree-search">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" className="tree-search-icon" aria-hidden>
            <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2" />
            <path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <Input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by title, why, done…"
            aria-label="Filter tasks"
          />
        </div>
        <Select value={sort} onChange={(e) => setSort(e.target.value as TreeSort)} className="tree-sort" aria-label="Sort">
          <option value="id">Sort: ID</option>
          <option value="status">Sort: Status</option>
        </Select>
        <span className="mono small muted tree-count-pill">
          {filtered} / {total}
        </span>
      </div>
    </Card>
  );
}

export default function TreeView({
  tasks,
  gates,
  taskId = null,
  q = '',
  status = 'all',
  sort = 'id',
  onRouteChange,
}: {
  tasks: TaskNode[];
  gates?: Record<string, { pass: number; reject: number }>;
  taskId?: string | null;
  q?: string;
  status?: TreeFilter;
  sort?: TreeSort;
  onRouteChange?: (patch: TreeRoutePatch) => void;
}) {
  const [copyError, setCopyError] = useState<string | null>(null);
  const filterRef = useRef<HTMLInputElement>(null);

  const setQ = (v: string) => onRouteChange?.({ q: v });
  const setF = (v: TreeFilter) => onRouteChange?.({ status: v });
  const setSort = (v: TreeSort) => onRouteChange?.({ sort: v });
  const setSelected = (id: string | null) => onRouteChange?.({ taskId: id });

  const byId = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);

  const filtered = useMemo(() => {
    let r = [...tasks];
    if (q.trim()) r = r.filter((t) => matchesQuery(t, q));
    if (status !== 'all') r = r.filter((t) => t.status === status);
    return sortTasks(r, sort);
  }, [tasks, q, status, sort]);

  const filteredIds = useMemo(() => new Set(filtered.map((t) => t.id)), [filtered]);

  /** When filtering, include ancestors so matching nodes remain reachable in the tree. */
  const visibleIds = useMemo(() => {
    if (!q.trim() && status === 'all') return new Set(tasks.map((t) => t.id));
    const vis = new Set(filteredIds);
    for (const id of filteredIds) {
      for (const a of ancestorIds(id, byId)) vis.add(a);
    }
    return vis;
  }, [tasks, filteredIds, byId, q, status]);

  const childrenMap = useMemo(() => {
    const visible = tasks.filter((t) => visibleIds.has(t.id));
    const kids = buildChildrenMap(visible);
    for (const [k, list] of kids) {
      kids.set(k, sortTasks(list, sort));
    }
    return kids;
  }, [tasks, visibleIds, sort]);

  const roots = childrenMap.get(null) ?? [];

  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const init = new Set<string>();
    for (const t of tasks) {
      if (parentKey(t.parent) == null) init.add(t.id);
    }
    for (const a of ancestorIds(taskId, new Map(tasks.map((x) => [x.id, x])))) {
      init.add(a);
    }
    return init;
  });

  // Ensure selected ancestors stay expanded when selection changes
  useEffect(() => {
    if (!taskId) return;
    const need = ancestorIds(taskId, byId);
    if (!need.length) return;
    setExpanded((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const id of need) {
        if (!next.has(id)) {
          next.add(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [taskId, byId]);

  // Default-expand new roots when task set grows
  useEffect(() => {
    setExpanded((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const t of tasks) {
        if (parentKey(t.parent) == null && !next.has(t.id)) {
          next.add(t.id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [tasks]);

  const flatVisible = useMemo(() => {
    const out: TaskNode[] = [];
    const walk = (nodes: TaskNode[]) => {
      for (const n of nodes) {
        out.push(n);
        const kids = childrenMap.get(n.id) ?? [];
        if (kids.length && expanded.has(n.id)) walk(kids);
      }
    };
    walk(roots);
    // Prefer depth-first of expanded tree; if filter left only matching leaves without expand, fall back
    if (out.length === 0 && filtered.length) return filtered;
    // When actively filtering, j/k among matching tasks in tree order
    if (q.trim() || status !== 'all') {
      return out.filter((t) => filteredIds.has(t.id));
    }
    return out;
  }, [roots, childrenMap, expanded, filtered, filteredIds, q, status]);

  const selected = taskId;
  const sel = useMemo(
    () =>
      filtered.find((t) => t.id === selected) ??
      tasks.find((t) => t.id === selected) ??
      flatVisible[0] ??
      filtered[0] ??
      tasks[0] ??
      null,
    [filtered, tasks, selected, flatVisible],
  );

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: tasks.length };
    for (const t of tasks) c[t.status] = (c[t.status] || 0) + 1;
    return c;
  }, [tasks]);

  useEffect(() => {
    if (!selected && flatVisible[0]) setSelected(flatVisible[0].id);
  }, [flatVisible, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onSearch = (e: Event) => setQ((e as CustomEvent).detail || '');
    const onFocus = () => {
      filterRef.current?.focus();
      filterRef.current?.select();
    };
    const onNav = (e: Event) => {
      const dir = (e as CustomEvent).detail as string;
      const list = flatVisible;
      if (!list.length) return;
      const idx = list.findIndex((t) => t.id === selected);
      if (dir === 'next') setSelected(list[Math.min(idx + 1, list.length - 1)]?.id ?? list[0].id);
      if (dir === 'prev') setSelected(list[Math.max(idx - 1, 0)]?.id ?? list[0].id);
    };
    window.addEventListener('super-search' as unknown as string, onSearch as EventListener);
    window.addEventListener('super-focus-search' as unknown as string, onFocus as EventListener);
    window.addEventListener('super-nav' as unknown as string, onNav as EventListener);
    return () => {
      window.removeEventListener('super-search' as unknown as string, onSearch as EventListener);
      window.removeEventListener('super-focus-search' as unknown as string, onFocus as EventListener);
      window.removeEventListener('super-nav' as unknown as string, onNav as EventListener);
    };
  }, [flatVisible, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyError(null);
    } catch (e) {
      setCopyError(userMessage(e));
    }
  };

  const toggleExpand = (id: string, e: MouseEvent) => {
    e.stopPropagation();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const doneCount = tasks.filter((t) => t.status === 'proven').length;
  const checkRejects = gates ? Object.values(gates).reduce((acc, g) => acc + g.reject, 0) : 0;
  const checkStrip = gates
    ? Object.entries(gates)
        .slice(0, 3)
        .map(([k, s]) => `${k} ${s.pass}:${s.reject}`)
        .join(' · ') || '—'
    : '—';

  const hasActiveFilters = Boolean(q.trim()) || status !== 'all';

  const renderRow = (t: TaskNode, depth: number): ReactNode => {
    const kids = childrenMap.get(t.id) ?? [];
    const hasKids = kids.length > 0;
    const isOpen = expanded.has(t.id);
    const isActive = sel?.id === t.id;
    const isMatch = filteredIds.has(t.id);

    return (
      <div key={t.id}>
        <button
          type="button"
          onClick={() => setSelected(t.id)}
          className={`tree-row${isActive ? ' is-active' : ''}${isMatch ? '' : ' is-dim'}`}
          style={{ paddingLeft: `calc(var(--space-2) + ${depth * 16}px)` }}
        >
          <span
            role="button"
            tabIndex={-1}
            onClick={(e) => (hasKids ? toggleExpand(t.id, e) : e.stopPropagation())}
            className={`tree-chevron${hasKids ? '' : ' is-leaf'}${hasKids && isOpen ? ' is-open' : ''}`}
            aria-hidden={!hasKids}
            aria-label={hasKids ? (isOpen ? 'Collapse' : 'Expand') : undefined}
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
              <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="mono tree-id">{t.id}</span>
          <span className="tree-row-body">
            <span className="tree-row-title">{t.title}</span>
            <span className="small muted tree-row-meta">
              <span className="truncate" style={{ maxWidth: 180 }}>
                {t.needs.length ? `${t.needs.length} deps` : 'no deps'}
                {hasKids ? ` · ${kids.length} child${kids.length === 1 ? '' : 'ren'}` : ''}
              </span>
              <span className="tree-dot" aria-hidden />
              <span className="truncate" style={{ maxWidth: 140 }}>
                {t.why || '—'}
              </span>
            </span>
          </span>
          <StatusBadge status={t.status} />
        </button>
        {hasKids && isOpen && (
          <div className="tree-row-kids">
            {kids.map((c) => renderRow(c, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="tree-view">
      <Toolbar
        q={q}
        setQ={setQ}
        f={status}
        setF={setF}
        sort={sort}
        setSort={setSort}
        counts={counts}
        total={tasks.length}
        filtered={filtered.length}
        inputRef={filterRef}
      />

      <Collapsible
        title="Dependency map"
        storageKey="tree-dag"
        meta={
          <span className="mono">
            {tasks.length} tasks · drag to pan · ⌘+wheel zoom
          </span>
        }
        compact
      >
        <DagGraph tasks={tasks} selected={selected} onSelect={setSelected} bare />
      </Collapsible>

      <div className="split-tree">
        <Card className="tree-list-card">
          <CardHead>
            <h3>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
                <path d="M2.5 5.5h11M2.5 8h11M2.5 10.5h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              </svg>{' '}
              Tasks
            </h3>
            <span className="head-meta mono">{filtered.length} shown</span>
          </CardHead>

          <div className="tree-list">
            {tasks.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden>
                  <svg viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M5.5 8h5M8 5.5v5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </div>
                <h4>No tasks yet</h4>
                <p>
                  Add a task:
                  <br />
                  <code>python3 -m super.cli task-add &quot;Title&quot; --done &quot;check&quot; --why &quot;reason&quot;</code>
                </p>
              </div>
            ) : filtered.length === 0 ? (
              <div className="empty">
                <div className="empty-icon" aria-hidden>
                  <svg viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M5.5 8h5M8 5.5v5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </div>
                <h4>No tasks match</h4>
                <p>Try a different filter or clear search.</p>
                <Button size="sm" onClick={() => onRouteChange?.({ q: '', status: 'all' })}>
                  Clear filters
                </Button>
              </div>
            ) : (
              <div className="tree-list-inner">
                {roots.map((t) => renderRow(t, 0))}
              </div>
            )}
          </div>

          <div className="table-foot" style={{ background: 'var(--bg-2)', flexWrap: 'wrap' }}>
            <span className="mono">
              {doneCount}/{tasks.length} done
            </span>
            <span aria-hidden>·</span>
            <span className="mono">checks: {checkStrip}</span>
            <span aria-hidden>·</span>
            <span className="mono">issues: {checkRejects}</span>
            {hasActiveFilters && (
              <Button
                size="sm"
                variant="default"
                style={{ marginLeft: 'auto', fontSize: 'var(--text-2xs)' }}
                onClick={() => onRouteChange?.({ q: '', status: 'all' })}
              >
                Clear filters
              </Button>
            )}
          </div>
        </Card>

        <div className="col-stack" style={{ overflow: 'auto' }}>
          {sel ? (
            <Card style={{ overflow: 'hidden' }}>
              <div className="panel-stack">
                <div className="tree-detail-head">
                  <div style={{ minWidth: 0 }}>
                    <div className="chip-row" style={{ marginBottom: 'var(--space-1)' }}>
                      <Badge variant="neutral" style={{ fontSize: 'var(--text-xs)' }}>
                        # {sel.id}
                      </Badge>
                      <StatusBadge status={sel.status} />
                      {sel.parent && (
                        <Badge variant="neutral">parent {sel.parent}</Badge>
                      )}
                    </div>
                    <h3 className="tree-detail-title">{sel.title}</h3>
                  </div>
                  <Badge variant="accent" style={{ fontSize: 'var(--text-xs)' }}>
                    {sel.needs.length} deps
                  </Badge>
                </div>

                <div className="chip-row">
                  <Button size="sm" variant="primary" onClick={() => navigate({ view: 'approve', taskId: sel.id })}>
                    Open in Review
                  </Button>
                  <Button size="sm" variant="default" onClick={() => navigate({ view: 'report' })}>
                    Open in Results
                  </Button>
                </div>

                <div className="col-stack">
                  {(
                    [
                      { k: 'Why it matters', v: sel.why || '—' },
                      { k: 'Done looks like', v: sel.done || '—' },
                      {
                        k: 'Depends on',
                        v: sel.needs.length ? sel.needs.join(', ') : 'Nothing',
                        mono: true,
                      },
                      {
                        k: 'Blocks',
                        v: sel.blocks?.length ? sel.blocks.join(', ') : '—',
                        mono: true,
                      },
                      {
                        k: 'Files',
                        v: sel.files?.length ? sel.files.join(', ') : '—',
                        mono: true,
                      },
                      {
                        k: 'Proof',
                        v: sel.proof || '(empty — not done yet)',
                        mono: true,
                        empty: !sel.proof,
                      },
                    ] as { k: string; v: string; mono?: boolean; empty?: boolean }[]
                  ).map(({ k, v, mono, empty }) => (
                    <div key={k} className="field-block">
                      <div className="field-block-label">{k}</div>
                      <div
                        className={`field-block-value${empty ? ' is-muted' : ''}`}
                        style={{
                          fontFamily: mono ? 'var(--font-mono)' : undefined,
                          fontStyle: empty ? 'italic' : undefined,
                        }}
                      >
                        {v}
                      </div>
                    </div>
                  ))}
                </div>
                {copyError && (
                  <div className="alert alert--error" style={{ fontSize: 'var(--text-sm)' }}>
                    {copyError}
                  </div>
                )}
              </div>

              <div className="table-foot" style={{ flexWrap: 'wrap' }}>
                <span className="mono small muted row gap-sm">
                  <span className={`status-dot ${sel.status}`} aria-hidden />
                  {statusLabel(sel.status)}
                </span>
                <span className="toolbar-actions" style={{ marginLeft: 'auto' }}>
                  <Button size="sm" variant="default" onClick={() => void copy(sel.id)}>
                    copy id
                  </Button>
                  <Button size="sm" variant="primary" onClick={() => void copy(sel.title)}>
                    copy title
                  </Button>
                </span>
              </div>
            </Card>
          ) : (
            <Card className="panel-pad" style={{ padding: 'var(--space-10)', textAlign: 'center', color: 'var(--fg-3)' }}>
              <div className="empty">
                <div className="empty-icon" aria-hidden>
                  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                    <path d="M8 6v3M8 11h.01" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                    <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2" />
                  </svg>
                </div>
                <p>Select a task to see details</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
