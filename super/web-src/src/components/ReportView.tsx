import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { TaskNode } from '../types';
import { StatusBadge } from './TreeView';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHead } from './ui/Card';
import { Collapsible } from './ui/Collapsible';
import { Progress } from './ui/Progress';
import { useVirtual } from '../hooks/useVirtual';
import { Alert } from './ui/Alert';

function Kpi({ label, value, sub, color, icon }: { label: string; value: string; sub: string; color: string; icon: React.ReactNode }) {
  return (
    <Card style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>{label}</span>
        <span style={{ width: 28, height: 28, borderRadius: 'var(--radius-sm)', background: 'var(--bg-3)', border: '1px solid var(--border)', display: 'grid', placeItems: 'center', color }}>{icon}</span>
      </div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: 'var(--tracking-tight)', lineHeight: 1, color }}>{value}</div>
      <div className="small muted" style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' }}>{sub}</div>
    </Card>
  );
}

export default function ReportView({
  tasks,
  gates,
  criticals,
}: {
  tasks: TaskNode[];
  gates: Record<string, { pass: number; reject: number }>;
  criticals: unknown[];
}) {
  const proven = tasks.filter((t) => t.status === 'proven').length;
  const total = tasks.length;
  const pct = total ? Math.round((proven / total) * 100) : 0;
  const gatePass = Object.values(gates).reduce((s, g) => s + g.pass, 0);
  const gateReject = Object.values(gates).reduce((s, g) => s + g.reject, 0);
  const totalGates = gatePass + gateReject;
  const passRate = totalGates ? Math.round((gatePass / totalGates) * 100) : 100;
  const waiting = tasks.filter((t) => t.status === 'waiting').length;
  const doing = tasks.filter((t) => t.status === 'doing').length;
  const blocked = tasks.filter((t) => t.status === 'blocked').length;

  const spark = [2, 4, 3, 6, 5, 8, gatePass || 1];
  const max = Math.max(...spark, 1);

  // Security substrate + spec + checklist — fetch for audit panels
  const [sbom, setSbom] = useState<{ packages: { name: string; version: string }[]; count: number } | null>(null);
  const [sink, setSink] = useState<{ entries: number; violations: unknown[]; clean: boolean } | null>(null);
  const [checklist, setChecklist] = useState<string[]>([]);
  const [waivers, setWaivers] = useState<unknown[]>([]);
  useEffect(() => {
    import('../api').then(({ api }) => {
      api.sbom().then(setSbom).catch(() => {});
      api.sink().then(setSink).catch(() => {});
      api.checklist().then((r) => setChecklist(r.checklist)).catch(() => {});
      api.waivers().then((r) => setWaivers(r.waivers as unknown[])).catch(() => {});
    });
  }, []);

  // Data-density: virtualization + column prefs + bulk + export
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cols, setCols] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('super_cols') || 'null') || { id: true, task: true, status: true, why: true, proof: true }; } catch { return { id: true, task: true, status: true, why: true, proof: true }; }
  });
  useEffect(() => { try { localStorage.setItem('super_cols', JSON.stringify(cols)); } catch {} }, [cols]);
  const tableRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const rowH = 40;
  const containerH = 380;
  const virt = useVirtual(tasks.length, rowH, containerH, scrollTop);
  const toggleCol = (k: string) => setCols((c) => ({ ...c, [k]: !c[k] }));
  const toggleSelect = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const selectAll = () => setSelected(selected.size === tasks.length ? new Set() : new Set(tasks.map((t) => t.id)));
  const exportCsv = () => {
    const keys = Object.keys(cols).filter((k) => (cols as Record<string,boolean>)[k]);
    const header = keys.join(',');
    const rows = tasks.map((t) => {
      const m: Record<string,string> = { id: t.id, task: `"${t.title.replace(/"/g,'""')}"`, status: t.status, why: `"${(t.why||'').replace(/"/g,'""')}"`, proof: `"${(t.proof||'').replace(/"/g,'""')}"` };
      return keys.map((k) => m[k] ?? '').join(',');
    }).join('\n');
    const blob = new Blob([header + '\n' + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'tasks.csv'; a.click(); URL.revokeObjectURL(url);
  };
  const bulkApprove = async () => {
    const ids = Array.from(selected);
    for (const id of ids) { try { await api.approve(id, 'bulk approved'); } catch {} }
    setSelected(new Set());
  };
  const [revertId, setRevertId] = useState('');
  const [revertMsg, setRevertMsg] = useState<string | null>(null);
  const doRevert = async (id: string) => {
    const target = id || revertId;
    if (!target) return;
    try {
      const r = await api.rollback(target);
      setRevertMsg(`Reopened ${r.reopened.length ? r.reopened.join(', ') : 'nothing'} — rolled back to ${target}`);
      setTimeout(()=> setRevertMsg(null), 3000);
      // refresh parent via reload
      window.dispatchEvent(new Event('super-refresh'));
    } catch (e) { setRevertMsg(String((e as Error).message)); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {/* KPI row */}
      <div className="kpi-grid">
        <Kpi label="Proven" value={`${proven}/${total || '—'}`} sub={`${pct}% complete · ${waiting} waiting · ${doing} doing`} color={pct === 100 ? 'var(--green)' : 'var(--fg-0)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>} />
        <Kpi label="Gate pass rate" value={`${passRate}%`} sub={`${gatePass} pass · ${gateReject} reject · ${totalGates || 0} total`} color={passRate >= 85 ? 'var(--green)' : passRate >= 60 ? 'var(--yellow)' : 'var(--red)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 14A6 6 0 108 2a6 6 0 000 12z" stroke="currentColor" strokeWidth="1.2"/><path d="M5 8h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>} />
        <Kpi label="Open criticals" value={String(criticals.length)} sub={criticals.length ? 'Needs triage — waivers expire, SAST/sink block writes' : 'All clear — no waivers or sink hits'} color={criticals.length ? 'var(--red)' : 'var(--green)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3l6 10H2L8 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M8 7v3M8 11h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>} />
        <Kpi label="Blocked" value={String(blocked)} sub={`${blocked ? 'Needs unblock · check needs graph' : 'No blocked nodes — DAG is flowing'}`} color={blocked ? 'var(--red)' : 'var(--fg-0)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 5.5l5 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>} />
      </div>

      {/* Provenance + gates */}
      <Collapsible title="Provenance & gates" className="collapsible-bare" storageKey="report-prov" meta={<span className="mono small muted">{proven}/{total} proven · {passRate}% gate pass</span>}>
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr .8fr', gap: 'var(--space-2)' }}>
        <Card style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>PROVENANCE</span>
            <span className="mono small" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>{proven} of {total} · leaf-only + fork-per-task</span>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            {/* Flat gauge — no conic gradient, solid ring + progress */}
            <div style={{ width: 80, height: 80, borderRadius: 'var(--radius-full)', background: 'var(--bg-1)', border: '1px solid var(--border)', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
              <div style={{ width: 68, height: 68, borderRadius: 'var(--radius-full)', background: 'var(--bg-2)', border: `3px solid ${pct === 100 ? 'var(--green)' : 'var(--accent)'}`, display: 'grid', placeItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, letterSpacing: 'var(--tracking-tight)', color: pct === 100 ? 'var(--green)' : 'var(--fg-0)' }}>{pct}<span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-3)' }}>%</span></div>
                  <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>proven</div>
                </div>
              </div>
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-1)' }}><span className="mono">Progress</span><span className="mono">{proven}/{total}</span></div>
                <Progress value={pct} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 'var(--space-2)' }}>
                {[
                  { k: 'waiting', v: waiting, c: 'var(--yellow)' },
                  { k: 'doing', v: doing, c: 'var(--blue)' },
                  { k: 'blocked', v: blocked, c: 'var(--red)' },
                ].map(({ k, v, c }) => (
                  <div key={k} style={{ padding: 'var(--space-2)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                    <div className="mono" style={{ fontWeight: 700, color: c }}>{v}</div>
                    <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-wide)' }}>{k}</div>
                  </div>
                ))}
              </div>
              <div className="small muted" style={{ fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>Done-state gate: report shows <span className="mono">done_ok</span> only when every leaf has a proof pointer. Waivers are time-boxed and audited.</div>
            </div>
          </div>
        </Card>

        <Card style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>GATE TREND</span>
            <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>{totalGates} events</Badge>
          </div>
          {/* sparkline — flat bars */}
          <div style={{ height: 56, display: 'flex', alignItems: 'end', gap: 4, padding: 'var(--space-2)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
            {spark.map((v, i) => (
              <div key={i} style={{ flex: 1, height: `${(v / max) * 100}%`, minHeight: 4, borderRadius: 'var(--radius-xs)', background: i === spark.length - 1 ? 'var(--accent)' : 'var(--bg-4)' }} />
            ))}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <Badge variant="proven" style={{ fontSize: 'var(--text-xs)' }}>{gatePass} pass</Badge>
            <Badge variant={gateReject ? 'blocked' : 'neutral'} style={{ fontSize: 'var(--text-xs)' }}>{gateReject} reject</Badge>
            <span className="mono small muted" style={{ marginLeft: 'auto', alignSelf: 'center' }}>{passRate}% pass</span>
          </div>
          <div className="small muted" style={{ fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>Catch-rate is per-gate (grounding, duplication, mutation…) — see breakdown below. Fatigued reviewers are escalated.</div>
        </Card>
      </div>
      </Collapsible>

      {/* Task table — virtualized + density controls */}
      <Card style={{ overflow: 'hidden' }}>
        <CardHead>
          <h3><svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M3 5h10M3 8h6M3 11h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg> Tasks · provenance ledger</h3>
          <span style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <span className="head-meta mono">{proven}/{total} proven · {selected.size ? `${selected.size} selected` : 'tap row to copy'}</span>
            <Button size="sm" variant="ghost" onClick={selectAll}>{selected.size === tasks.length ? 'clear' : 'all'}</Button>
            {selected.size > 0 && <Button size="sm" variant="primary" onClick={bulkApprove}>bulk approve</Button>}
            <Button size="sm" variant="default" onClick={exportCsv}>export CSV</Button>
            <input value={revertId} onChange={e=> setRevertId(e.target.value)} placeholder="revert to id" style={{ width: 90, fontSize: 'var(--text-xs)', padding: '4px 6px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'var(--bg-1)', fontFamily: 'var(--font-mono)' }} />
            <Button size="sm" variant="default" onClick={()=> void doRevert('')}>revert</Button>
          </span>
        </CardHead>
        <div style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-1)', padding: '1px var(--space-1)' }}>
          <Collapsible title="Columns" className="collapsible-bare" compact defaultOpen={false} meta={<span className="mono small muted">{Object.values(cols).filter(Boolean).length}/5 shown</span>}>
            <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', paddingBottom: 'var(--space-2)' }}>
              {(['id','task','status','why','proof'] as const).map((k) => (
                <label key={k} className="mono small" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 'var(--text-xs)' }}>
                  <input type="checkbox" checked={(cols as Record<string,boolean>)[k]} onChange={() => toggleCol(k)} style={{ accentColor: 'var(--accent)' }} /> {k}
                </label>
              ))}
            </div>
          </Collapsible>
        </div>
        <div
          ref={tableRef}
          onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
          style={{ overflow: 'auto', maxHeight: containerH, position: 'relative' }}
        >
          <table style={{ width: '100%' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
              <tr>
                <th style={{ width: 36 }}><input type="checkbox" checked={selected.size === tasks.length && tasks.length>0} onChange={selectAll} /></th>
                {cols.id && <th style={{ width: 56 }}>ID</th>}
                {cols.task && <th>TASK</th>}
                {cols.status && <th>STATUS</th>}
                {cols.why && <th>WHY</th>}
                {cols.proof && <th>PROOF</th>}
                <th style={{ width: 60 }}>REVERT</th>
              </tr>
            </thead>
            <tbody>
              {revertMsg && <tr><td colSpan={7} style={{ padding: 'var(--space-2)' }}><Alert variant="success" style={{ fontSize: 'var(--text-xs)' }}>{revertMsg}</Alert></td></tr>}
              {tasks.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 'var(--space-8)', color: 'var(--fg-3)' }}>No tasks — <code>python3 -m super.cli task-add "Title" --done "check"</code></td></tr>
              ) : (
                <>
                  {virt.start > 0 && <tr style={{ height: virt.offset }}><td colSpan={7} style={{ padding: 0, border: 'none' }} /></tr>}
                  {tasks.slice(virt.start, virt.end).map((t) => (
                    <tr key={t.id} style={{ height: rowH, cursor: t.proof ? 'pointer' : 'default', background: selected.has(t.id) ? 'var(--accent-soft)' : undefined }} onClick={() => { if (t.proof) navigator.clipboard.writeText(t.proof).catch(() => {}); }}>
                      <td><input type="checkbox" checked={selected.has(t.id)} onChange={() => toggleSelect(t.id)} onClick={(e) => e.stopPropagation()} /></td>
                      {cols.id && <td className="mono muted" style={{ fontWeight: 600 }}>{t.id}</td>}
                      {cols.task && <td style={{ fontWeight: 550, color: 'var(--fg-0)', maxWidth: 280 }}><div className="truncate" title={t.title}>{t.title}</div><div className="mono small muted" style={{ fontSize: 'var(--text-2xs)', marginTop: 2 }}>{t.needs.length ? t.needs.join(', ') : 'leaf'}{t.blocks?.length? ` · blocks ${t.blocks.join(',')}`:''}{t.files?.length? ` · ${t.files[0]}`:''}</div></td>}
                      {cols.status && <td><StatusBadge status={t.status} /></td>}
                      {cols.why && <td style={{ maxWidth: 220, color: 'var(--fg-2)', fontSize: 'var(--text-sm)' }}><span className="truncate" title={t.why}>{t.why || '—'}</span></td>}
                      {cols.proof && <td style={{ maxWidth: 240 }}>{t.proof ? <code className="mono" style={{ fontSize: 'var(--text-xs)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', display: 'inline-block' }}>{t.proof}</code> : <span className="muted" style={{ fontStyle: 'italic', fontSize: 'var(--text-sm)' }}>—</span>}</td>}
                      <td><Button size="sm" variant="ghost" onClick={(e)=> { e.stopPropagation(); void doRevert(t.id); }} style={{ fontSize: 'var(--text-xs)', padding: '2px 6px' }}>revert</Button></td>
                    </tr>
                  ))}
                  {virt.end < tasks.length && <tr style={{ height: virt.total - virt.offset - (virt.end - virt.start) * rowH }}><td colSpan={7} style={{ padding: 0, border: 'none' }} /></tr>}
                </>
              )}
            </tbody>
          </table>
        </div>
        <div className="small muted" style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: 'var(--space-2)' }}>
          <span className="mono">{tasks.length} rows · virtualized {virt.start}-{virt.end}</span>
          <span style={{ marginLeft: 'auto' }} className="mono">density: {rowH}px row · CSV · bulk</span>
        </div>
      </Card>

      {/* Gate breakdown */}
      <Collapsible title="Gate breakdown" storageKey="report-gates" compact meta={<span className="mono small muted" style={{ fontSize: 'var(--text-xs)' }}>{Object.keys(gates).length} gates · best-of-5 + early-abort</span>}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 'var(--space-2)' }}>
          {Object.entries(gates).map(([gate, s]) => {
            const tot = s.pass + s.reject;
            const pr = tot ? (s.pass / tot) * 100 : 0;
            return (
              <div key={gate} style={{ padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--fg-1)' }}>{gate}</span>
                  <span className="mono" style={{ fontSize: 'var(--text-xs)' }}><span style={{ color: 'var(--green)', fontWeight: 700 }}>{s.pass}</span><span className="muted"> / </span><span style={{ color: s.reject ? 'var(--red)' : 'var(--fg-3)', fontWeight: 700 }}>{s.reject}</span></span>
                </div>
                <Progress value={pr} variant={s.reject ? 'warning' : 'success'} />
                <div className="mono small muted" style={{ fontSize: 'var(--text-2xs)' }}>{s.reject ? `${Math.round((s.reject / tot) * 100)}% rejected` : 'no rejections'} · {tot} events</div>
              </div>
            );
          })}
          {Object.keys(gates).length === 0 && <div className="small muted" style={{ padding: 'var(--space-3)', background: 'var(--bg-1)', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>No gate events yet — chat or write to generate telemetry</div>}
        </div>
      </Collapsible>

      {/* Security substrate — SBOM, sink, waivers, checklist (doc 02 §6, 03 §5) */}
      <Collapsible
        title="Security substrate"
        storageKey="report-sec"
        defaultOpen={false}
        compact
        meta={<span className="mono small muted" style={{ fontSize: 'var(--text-xs)' }}>SBOM {sbom?.count ?? 0} · sink {sink?.entries ?? 0} · waivers {waivers.length}</span>}
      >
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-2)' }}>
        <Card style={{ padding: 'var(--space-3)' }}>
          <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-2)' }}>SBOM — {sbom?.count ?? 0} packages</div>
          {sbom && sbom.packages.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 140, overflow: 'auto' }}>
              {sbom.packages.slice(0, 8).map((p) => (
                <div key={`${p.name}@${p.version}`} className="mono" style={{ fontSize: 'var(--text-xs)', display: 'flex', justifyContent: 'space-between', padding: '4px 8px', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)' }}>
                  <span>{p.name}</span><span className="muted">{p.version || 'unpinned'}</span>
                </div>
              ))}
              {sbom.count > 8 && <span className="small muted">+{sbom.count - 8} more</span>}
            </div>
          ) : (
            <div className="small muted">No SBOM yet — run any task to generate from lockfiles</div>
          )}
        </Card>
        <Card style={{ padding: 'var(--space-3)' }}>
          <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-2)' }}>SINK AUDIT — {sink?.entries ?? 0} entries</div>
          {sink ? (
            sink.clean ? <Badge variant="proven">clean — no untrusted network-out</Badge> : <Badge variant="blocked">{sink.violations.length} violations</Badge>
          ) : (
            <span className="small muted">Loading…</span>
          )}
          {sink && sink.violations.length > 0 && (
            <div style={{ marginTop: 'var(--space-2)', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {(sink.violations as Array<{ kind: string; target: string; taint: string }>).slice(0, 3).map((v, i) => (
                <div key={i} className="mono" style={{ fontSize: 'var(--text-xs)', padding: '4px 8px', background: 'var(--red-bg)', border: '1px solid var(--red-border)', borderRadius: 'var(--radius-xs)', color: 'var(--red)' }}>{v.kind} → {v.target} [{v.taint}]</div>
              ))}
            </div>
          )}
        </Card>
        <Card style={{ padding: 'var(--space-3)' }}>
          <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-2)' }}>REVIEWER CHECKLIST — mined</div>
          {checklist.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {checklist.slice(0, 6).map((c) => (
                <div key={c} style={{ fontSize: 'var(--text-sm)', padding: '6px 8px', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-xs)' }}>{c}</div>
              ))}
            </div>
          ) : (
            <span className="small muted">No rejections yet — checklist learns from past rejections</span>
          )}
        </Card>
        <Card style={{ padding: 'var(--space-3)' }}>
          <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-2)' }}>WAIVERS — {waivers.length} open</div>
          {waivers.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 140, overflow: 'auto' }}>
              {(waivers as Array<{ text?: string; expires?: string }>).slice(0, 4).map((w, i) => (
                <div key={i} className="mono" style={{ fontSize: 'var(--text-xs)', padding: '6px 8px', background: 'var(--yellow-bg)', border: '1px solid var(--yellow-border)', borderRadius: 'var(--radius-xs)', color: 'var(--yellow)' }}>{String((w as { text?: string }).text || JSON.stringify(w)).slice(0, 80)}{(w as { expires?: string }).expires ? ` → ${ (w as { expires?: string }).expires}` : ''}</div>
              ))}
            </div>
          ) : (
            <Badge variant="proven">no waivers — done-state unblocked</Badge>
          )}
        </Card>
      </div>
      </Collapsible>

      {/* Criticals */}
      {criticals.length > 0 && (
        <Collapsible
          title={`Open criticals — ${criticals.length}`}
          storageKey="report-criticals"
          compact
          badge={<Badge variant="blocked" style={{ fontSize: 'var(--text-2xs)' }}>{criticals.length}</Badge>}
          meta={<span className="mono small" style={{ color: 'var(--red)', fontSize: 'var(--text-xs)' }}>require waiver or fix</span>}
          style={{ borderColor: 'var(--red-border)' }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {(criticals as Array<{ text?: string; layer?: string; message?: string; severity?: string }>).map((c, i) => (
              <div key={i} style={{ padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-1)', border: '1px solid var(--red-border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-base)', color: 'var(--fg-1)', display: 'flex', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
                <span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: 'var(--red)', marginTop: 7, flexShrink: 0 }} aria-hidden />
                <span style={{ flex: 1, lineHeight: 'var(--leading-normal)' }}>{c.text || c.layer || c.message || JSON.stringify(c)}</span>
                <Badge variant="blocked" style={{ fontSize: 'var(--text-2xs)' }}>{c.severity || 'critical'}</Badge>
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', padding: 'var(--space-1) var(--space-1)' }}>
        <span className="mono">SUPER v1.0 · all gates enforced</span>
        <span aria-hidden>·</span>
        <span>Ledger: <code style={{ fontSize: 'var(--text-2xs)' }}>.super/gate.log.jsonl</code></span>
        <span style={{ marginLeft: 'auto' }} className="mono">envelope · Best-of-5 · stall 3</span>
      </div>
    </div>
  );
}
