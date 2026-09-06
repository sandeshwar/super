import { useEffect, useRef, useState, useMemo } from 'react';
import type { TaskNode } from '../../types';

type Pos = { x: number; y: number };

// Simple layered layout: rank by depth (needs graph), x by order.
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
  const colW = 200, rowH = 64, padX = 24, padY = 24;
  // sort within layer by id for stability
  Array.from(layers.entries()).sort((a,b)=>a[0]-b[0]).forEach(([d, ids]) => {
    ids.sort().forEach((id, i) => {
      pos.set(id, { x: padX + d * colW, y: padY + i * rowH });
    });
  });
  // adjust y to avoid overlap across layers: compact
  return pos;
}

export function DagGraph({ tasks, onSelect, selected }: { tasks: TaskNode[]; onSelect: (id: string) => void; selected?: string | null }) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  const pos = useMemo(() => layout(tasks), [tasks]);
  const bounds = useMemo(() => {
    if (!pos.size) return { w: 400, h: 200 };
    let maxX = 0, maxY = 0;
    pos.forEach((p) => { maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); });
    return { w: maxX + 160, h: maxY + 80 };
  }, [pos]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.07 : 0.07;
        setZoom((z) => Math.min(1.6, Math.max(0.6, z + delta)));
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = true;
    last.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging.current) return;
    const dx = e.clientX - last.current.x;
    const dy = e.clientY - last.current.y;
    last.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  };
  const onPointerUp = () => { dragging.current = false; };

  const statusColor = (s: string) => s === 'proven' ? 'var(--green)' : s === 'blocked' ? 'var(--red)' : s === 'doing' ? 'var(--blue)' : s === 'waiting' ? 'var(--yellow)' : 'var(--fg-3)';

  if (tasks.length === 0) {
    return <div className="empty" style={{ padding: 'var(--space-6)' }}><p className="small muted">No tasks to graph</p></div>;
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden', background: 'var(--bg-1)', position: 'relative' }}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--border)', alignItems: 'center', background: 'var(--bg-2)' }}>
        <span className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>DAG</span>
        <span className="mono small muted">{tasks.length} nodes · drag to pan · ⌘+wheel zoom</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
          <button className="btn btn-sm" onClick={() => setZoom((z) => Math.min(1.6, z + 0.12))}>+</button>
          <button className="btn btn-sm" onClick={() => setZoom((z) => Math.max(0.6, z - 0.12))}>−</button>
          <button className="btn btn-sm" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>reset</button>
        </span>
      </div>
      <div style={{ overflow: 'hidden', height: 360, cursor: dragging.current ? 'grabbing' : 'grab' }} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
        <svg
          ref={svgRef}
          width={bounds.w * zoom}
          height={bounds.h * zoom}
          viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${bounds.w} ${bounds.h}`}
          style={{ display: 'block', background: 'var(--bg-1)' }}
          role="img"
          aria-label="Task DAG"
        >
          {/* edges */}
          {tasks.map((t) =>
            t.needs.map((need) => {
              const a = pos.get(need);
              const b = pos.get(t.id);
              if (!a || !b) return null;
              const ax = a.x + 136, ay = a.y + 16;
              const bx = b.x, by = b.y + 16;
              const mid = (ax + bx) / 2;
              return <path key={`${need}->${t.id}`} d={`M ${ax} ${ay} C ${mid} ${ay}, ${mid} ${by}, ${bx} ${by}`} fill="none" stroke="var(--border-strong)" strokeWidth={1.2} />;
            })
          )}
          {/* nodes */}
          {tasks.map((t) => {
            const p = pos.get(t.id);
            if (!p) return null;
            const sel = selected === t.id;
            return (
              <g key={t.id} onClick={() => onSelect(t.id)} style={{ cursor: 'pointer' }} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onSelect(t.id)}>
                <rect x={p.x} y={p.y} width={136} height={32} rx={8} fill={sel ? 'var(--accent-soft)' : 'var(--bg-2)'} stroke={sel ? 'var(--accent-border)' : 'var(--border)'} strokeWidth={sel ? 1.4 : 1} />
                <circle cx={p.x + 12} cy={p.y + 16} r={5} fill={statusColor(t.status)} stroke="var(--bg-1)" strokeWidth={1.2} />
                <text x={p.x + 24} y={p.y + 12} fontSize={10} fontFamily="var(--font-mono)" fill="var(--fg-2)">{t.id}</text>
                <text x={p.x + 24} y={p.y + 24} fontSize={11} fontWeight={500} fill={sel ? 'var(--fg-0)' : 'var(--fg-1)'}>{t.title.slice(0, 14)}{t.title.length > 14 ? '…' : ''}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="small muted" style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--green)' }} /> proven</span>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--yellow)' }} /> waiting</span>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--blue)' }} /> doing</span>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span style={{ width: 8, height: 8, borderRadius: 99, background: 'var(--red)' }} /> blocked</span>
      </div>
    </div>
  );
}
