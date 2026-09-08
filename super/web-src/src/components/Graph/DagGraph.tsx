import { useEffect, useRef, useState, useMemo, useCallback, useId } from 'react';
import type { TaskNode } from '../../types';
import { Button } from '../ui/Button';

type Pos = { x: number; y: number };

const NODE_W = 156;
const NODE_H = 44;
const COL_W = 220;
const ROW_H = 72;
const PAD_X = 28;
const PAD_Y = 28;
const TITLE_MAX = 22;
/** Hardcoded — SVG filters don't reliably resolve CSS vars */
const SEL_GLOW = '#2ec4a0';

function layout(tasks: TaskNode[]): Map<string, Pos> {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const depth = new Map<string, number>();
  const visit = (id: string, seen = new Set<string>()): number => {
    if (depth.has(id)) return depth.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const t = byId.get(id);
    if (!t || !t.needs.length) { depth.set(id, 0); return 0; }
    const d = 1 + Math.max(0, ...t.needs.map((n) => (byId.has(n) ? visit(n, new Set(seen)) : 0)));
    depth.set(id, d);
    return d;
  };
  tasks.forEach((t) => visit(t.id));
  const layers = new Map<number, string[]>();
  tasks.forEach((t) => {
    const d = depth.get(t.id) ?? 0;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d)!.push(t.id);
  });
  const pos = new Map<string, Pos>();
  Array.from(layers.entries()).sort((a, b) => a[0] - b[0]).forEach(([d, ids]) => {
    ids.sort().forEach((id, i) => {
      pos.set(id, { x: PAD_X + d * COL_W, y: PAD_Y + i * ROW_H });
    });
  });
  return pos;
}

function statusColor(s: string) {
  return s === 'proven' ? 'var(--green)'
    : s === 'blocked' ? 'var(--red)'
    : s === 'doing' ? 'var(--blue)'
    : s === 'waiting' ? 'var(--yellow)'
    : 'var(--fg-3)';
}

function truncate(title: string, max = TITLE_MAX) {
  return title.length > max ? `${title.slice(0, max - 1)}…` : title;
}

export function DagGraph({ tasks, onSelect, selected, bare }: { tasks: TaskNode[]; onSelect: (id: string) => void; selected?: string | null; bare?: boolean }) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const userAdjusted = useRef(false);
  const glowId = useId().replace(/:/g, '');

  const pos = useMemo(() => layout(tasks), [tasks]);
  const bounds = useMemo(() => {
    if (!pos.size) return { w: 400, h: 200 };
    let maxX = 0, maxY = 0;
    pos.forEach((p) => { maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); });
    return { w: maxX + NODE_W + PAD_X, h: maxY + NODE_H + PAD_Y };
  }, [pos]);

  const fit = useCallback((force = false) => {
    const vp = viewportRef.current;
    if (!vp || !bounds.w) return false;
    const vw = vp.clientWidth;
    const vh = vp.clientHeight;
    if (vw < 8 || vh < 8) return false;
    if (!force && userAdjusted.current) return true;
    const pad = 24;
    const zx = (vw - pad) / bounds.w;
    const zy = (vh - pad) / bounds.h;
    const z = Math.min(1.2, Math.max(0.55, Math.min(zx, zy)));
    setZoom(z);
    setPan({
      x: (vw - bounds.w * z) / 2,
      y: (vh - bounds.h * z) / 2,
    });
    return true;
  }, [bounds.h, bounds.w]);

  // Auto-fit on mount / when graph bounds change; skip if user panned/zoomed
  useEffect(() => {
    userAdjusted.current = false;
    let cancelled = false;
    let tries = 0;
    const attempt = () => {
      if (cancelled) return;
      if (fit(true) || tries++ > 12) return;
      requestAnimationFrame(attempt);
    };
    requestAnimationFrame(attempt);
    return () => { cancelled = true; };
  }, [fit, tasks.length, bounds.w, bounds.h]);

  // Re-fit when viewport becomes measurable (e.g. collapsible opens / resize)
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      if (!userAdjusted.current) fit(true);
    });
    ro.observe(vp);
    return () => ro.disconnect();
  }, [fit]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        userAdjusted.current = true;
        const delta = e.deltaY > 0 ? -0.07 : 0.07;
        setZoom((z) => Math.min(1.6, Math.max(0.55, z + delta)));
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as Element).closest('[data-node]')) return;
    dragging.current = true;
    setIsDragging(true);
    last.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    userAdjusted.current = true;
    const dx = e.clientX - last.current.x;
    const dy = e.clientY - last.current.y;
    last.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  };
  const onPointerUp = () => {
    dragging.current = false;
    setIsDragging(false);
  };

  if (tasks.length === 0) {
    return (
      <div className="empty">
        <p className="small muted">No tasks to graph</p>
      </div>
    );
  }

  const filterUrl = `url(#${glowId})`;

  return (
    <div className={bare ? 'dag dag--bare' : 'dag'}>
      <div className="dag-toolbar">
        <span className="dag-label">DAG</span>
        {!bare && <span className="mono small muted">{tasks.length} nodes · drag to pan · ⌘+wheel zoom</span>}
        <span className="dag-controls">
          <Button size="icon-sm" variant="ghost" aria-label="Zoom in" onClick={() => { userAdjusted.current = true; setZoom((z) => Math.min(1.6, z + 0.12)); }}>+</Button>
          <Button size="icon-sm" variant="ghost" aria-label="Zoom out" onClick={() => { userAdjusted.current = true; setZoom((z) => Math.max(0.55, z - 0.12)); }}>−</Button>
          <Button size="sm" variant="ghost" onClick={() => { userAdjusted.current = false; fit(true); }}>Fit</Button>
        </span>
      </div>
      <div
        ref={viewportRef}
        className="dag-viewport"
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <svg
          ref={svgRef}
          width={bounds.w * zoom}
          height={bounds.h * zoom}
          viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${bounds.w} ${bounds.h}`}
          className="dag-svg"
          role="img"
          aria-label="Task DAG"
        >
          <defs>
            <filter id={glowId} x="-20%" y="-40%" width="140%" height="180%">
              <feDropShadow dx="0" dy="0" stdDeviation="3" floodColor={SEL_GLOW} floodOpacity="0.45" />
            </filter>
          </defs>
          {tasks.map((t) =>
            t.needs.map((need) => {
              const a = pos.get(need);
              const b = pos.get(t.id);
              if (!a || !b) return null;
              const ax = a.x + NODE_W;
              const ay = a.y + NODE_H / 2;
              const bx = b.x;
              const by = b.y + NODE_H / 2;
              const mid = (ax + bx) / 2;
              return (
                <path
                  key={`${need}->${t.id}`}
                  d={`M ${ax} ${ay} C ${mid} ${ay}, ${mid} ${by}, ${bx} ${by}`}
                  fill="none"
                  stroke="var(--border-strong)"
                  strokeWidth={1.35}
                  strokeOpacity={0.85}
                />
              );
            })
          )}
          {tasks.map((t) => {
            const p = pos.get(t.id);
            if (!p) return null;
            const sel = selected === t.id;
            const sc = statusColor(t.status);
            return (
              <g
                key={t.id}
                data-node
                onClick={() => onSelect(t.id)}
                style={{ cursor: 'pointer' }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && onSelect(t.id)}
              >
                <title>{`${t.id} · ${t.title} · ${t.status}`}</title>
                <rect
                  x={p.x}
                  y={p.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={10}
                  fill={sel ? 'var(--accent-soft)' : 'var(--bg-2)'}
                  stroke={sel ? 'var(--accent-border)' : 'var(--border)'}
                  strokeWidth={sel ? 1.5 : 1}
                  filter={sel ? filterUrl : undefined}
                />
                <rect x={p.x} y={p.y} width={4} height={NODE_H} rx={2} fill={sc} />
                <text x={p.x + 14} y={p.y + 16} fontSize={10} fontFamily="var(--font-mono)" fill="var(--fg-3)">{t.id}</text>
                <text x={p.x + 14} y={p.y + 32} fontSize={12} fontWeight={600} fill={sel ? 'var(--fg-0)' : 'var(--fg-1)'}>
                  {truncate(t.title)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="dag-legend">
        <span><i style={{ background: 'var(--green)' }} /> proven</span>
        <span><i style={{ background: 'var(--yellow)' }} /> waiting</span>
        <span><i style={{ background: 'var(--blue)' }} /> doing</span>
        <span><i style={{ background: 'var(--red)' }} /> blocked</span>
      </div>
    </div>
  );
}
