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
    <Card className="kpi-card">
      <div className="section-head">
        <span className="section-label">{label}</span>
        <span className="kpi-icon" style={{ color }}>{icon}</span>
      </div>
      <div className="kpi-value" style={{ color }}>{value}</div>
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
  const [bulkNote, setBulkNote] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const bulkApprove = async () => {
    const ids = Array.from(selected);
    if (!ids.length) return;
    const note = bulkNote.trim();
    if (!note) {
      setBulkMsg('Add a proof note before approving selected tasks.');
      return;
    }
    if (!window.confirm(`Mark ${ids.length} task${ids.length !== 1 ? 's' : ''} done with this proof?\n\n${note}`)) return;
    setBulkBusy(true);
    setBulkMsg(null);
    const failed: string[] = [];
    for (const id of ids) {
      try { await api.approve(id, note); }
      catch { failed.push(id); }
    }
    setSelected(new Set());
    setBulkNote('');
    setBulkBusy(false);
    if (failed.length) setBulkMsg(`Done for ${ids.length - failed.length}; failed: ${failed.join(', ')}`);
    else setBulkMsg(`Marked ${ids.length} task${ids.length !== 1 ? 's' : ''} done`);
    window.dispatchEvent(new Event('super-refresh'));
    setTimeout(() => setBulkMsg(null), 4000);
  };
  const [revertId, setRevertId] = useState('');
  const [revertMsg, setRevertMsg] = useState<string | null>(null);
  const [critKey, setCritKey] = useState(0);
  useEffect(() => {
    const h = () => {
      try { localStorage.setItem('super_collapse_report-criticals', '1'); } catch { /* ignore */ }
      setCritKey((k) => k + 1);
      window.setTimeout(() => document.getElementById('report-criticals')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60);
    };
    window.addEventListener('super-expand-criticals' as unknown as string, h as EventListener);
    return () => window.removeEventListener('super-expand-criticals' as unknown as string, h as EventListener);
  }, []);
  const doRevert = async (id: string) => {
    const target = id || revertId;
    if (!target) return;
    try {
      const r = await api.rollback(target);
      setRevertMsg(`Reopened ${r.reopened.length ? r.reopened.join(', ') : 'nothing'} — rolled back to ${target}`);
      setTimeout(()=> setRevertMsg(null), 3000);
      window.dispatchEvent(new Event('super-refresh'));
    } catch (e) { setRevertMsg(String((e as Error).message)); }
  };

  return (
    <div className="view-stack">
      <div className="kpi-grid">
        <Kpi label="Done" value={`${proven}/${total || '—'}`} sub={`${pct}% finished · ${waiting} waiting · ${doing} in progress`} color={pct === 100 ? 'var(--green)' : 'var(--fg-0)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>} />
        <Kpi label="Checks passed" value={`${passRate}%`} sub={`${gatePass} passed · ${gateReject} failed · ${totalGates || 0} total`} color={passRate >= 85 ? 'var(--green)' : passRate >= 60 ? 'var(--yellow)' : 'var(--red)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 14A6 6 0 108 2a6 6 0 000 12z" stroke="currentColor" strokeWidth="1.2"/><path d="M5 8h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>} />
        <Kpi label="Open problems" value={String(criticals.length)} sub={criticals.length ? 'Needs a fix or an approved exception' : 'No open problems'} color={criticals.length ? 'var(--red)' : 'var(--green)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3l6 10H2L8 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M8 7v3M8 11h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>} />
        <Kpi label="Blocked" value={String(blocked)} sub={blocked ? 'Waiting on other tasks' : 'Nothing blocked'} color={blocked ? 'var(--red)' : 'var(--fg-0)'} icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 5.5l5 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>} />
      </div>

      <Collapsible title="Progress & checks" className="collapsible-bare" storageKey="report-prov" meta={<span className="mono small muted">{proven}/{total} done · {passRate}% checks ok</span>}>
      <div className="split-prov">
        <Card className="panel-stack">
          <div className="section-head">
            <span className="section-label">Progress</span>
            <span className="mono small" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>{proven} of {total} done</span>
          </div>
          <div className="progress-row">
            <div className="gauge">
              <div className={`gauge-ring${pct === 100 ? ' is-done' : ''}`}>
                <div style={{ textAlign: 'center' }}>
                  <div className="gauge-pct">{pct}<span>%</span></div>
                  <div className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>done</div>
                </div>
              </div>
            </div>
            <div className="col-stack" style={{ flex: 1 }}>
              <div>
                <div className="section-head" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-1)' }}><span className="mono">Progress</span><span className="mono">{proven}/{total}</span></div>
                <Progress value={pct} />
              </div>
              <div className="stat-tiles">
                {[
                  { k: 'waiting', v: waiting, c: 'var(--yellow)' },
                  { k: 'doing', v: doing, c: 'var(--blue)' },
                  { k: 'blocked', v: blocked, c: 'var(--red)' },
                ].map(({ k, v, c }) => (
                  <div key={k} className="stat-tile">
                    <div className="mono" style={{ fontWeight: 700, color: c, fontSize: 'var(--text-base)' }}>{v}</div>
                    <div className="mono">{k}</div>
                  </div>
                ))}
              </div>
              <div className="small muted" style={{ fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>A task counts as done only when it has a proof note. Temporary exceptions expire and stay visible.</div>
            </div>
          </div>
        </Card>

        <Card className="panel-stack check-trend">
          <div className="section-head">
            <span className="section-label">Check split</span>
            <Badge variant="neutral" style={{ fontSize: 'var(--text-2xs)' }}>{totalGates} events</Badge>
          </div>
          {totalGates === 0 ? (
            <div className="check-split is-empty">No check events yet</div>
          ) : (
            <div className="check-split" role="img" aria-label={`${gatePass} passed, ${gateReject} rejected`}>
              {gatePass > 0 && (
                <div className="check-split-pass" style={{ flex: gatePass }}>
                  <span className="check-split-label">{gatePass}</span>
                </div>
              )}
              {gateReject > 0 && (
                <div className="check-split-reject" style={{ flex: gateReject }}>
                  <span className="check-split-label">{gateReject}</span>
                </div>
              )}
            </div>
          )}
          <div className="chip-row">
            <Badge variant="proven" style={{ fontSize: 'var(--text-xs)' }}>{gatePass} pass</Badge>
            <Badge variant={gateReject ? 'blocked' : 'neutral'} style={{ fontSize: 'var(--text-xs)' }}>{gateReject} reject</Badge>
            <span className="mono small muted" style={{ marginLeft: 'auto' }}>{passRate}% pass</span>
          </div>
          <div className="small muted" style={{ fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>Pass/reject totals across all checks. Per-type breakdown is below.</div>
        </Card>
      </div>
      </Collapsible>

      <Card style={{ overflow: 'hidden' }}>
        <CardHead>
          <h3>All tasks</h3>
          <span className="toolbar-actions">
            <span className="head-meta mono">{proven}/{total} done · {selected.size ? `${selected.size} selected` : 'select rows to act'}</span>
            <Button size="sm" variant="ghost" onClick={selectAll}>{selected.size === tasks.length ? 'Clear' : 'Select all'}</Button>
            {selected.size > 0 && (
              <>
                <input
                  value={bulkNote}
                  onChange={(e) => setBulkNote(e.target.value)}
                  placeholder="Proof note for selected…"
                  aria-label="Proof note for bulk approve"
                  className="input-compact"
                />
                <Button size="sm" variant="primary" disabled={bulkBusy} onClick={() => void bulkApprove()}>{bulkBusy ? 'Working…' : 'Mark selected done'}</Button>
              </>
            )}
            <Button size="sm" variant="default" onClick={exportCsv}>Export CSV</Button>
            <input value={revertId} onChange={e=> setRevertId(e.target.value)} placeholder="Undo to id" aria-label="Task id to undo from" className="input-compact mono" />
            <Button size="sm" variant="default" onClick={()=> void doRevert('')}>Undo</Button>
          </span>
        </CardHead>
        {(bulkMsg || revertMsg) && (
          <div className="table-msg">
            {bulkMsg && <Alert variant={bulkMsg.startsWith('Done') || bulkMsg.startsWith('Marked') ? 'success' : 'warning'} style={{ fontSize: 'var(--text-xs)' }}>{bulkMsg}</Alert>}
            {revertMsg && <Alert variant="success" style={{ fontSize: 'var(--text-xs)' }}>{revertMsg}</Alert>}
          </div>
        )}
        <div style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-1)', padding: '1px var(--space-1)' }}>
          <Collapsible title="Columns" className="collapsible-bare" compact defaultOpen={false} meta={<span className="mono small muted">{Object.values(cols).filter(Boolean).length}/5 shown</span>}>
            <div className="chip-row" style={{ paddingBottom: 'var(--space-2)' }}>
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
                <th style={{ width: 60 }}>UNDO</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: 'center', padding: 'var(--space-8)', color: 'var(--fg-3)' }}>No tasks yet</td></tr>
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
                      <td><Button size="sm" variant="ghost" onClick={(e)=> { e.stopPropagation(); void doRevert(t.id); }} style={{ fontSize: 'var(--text-xs)', padding: '2px 6px' }}>Undo</Button></td>
                    </tr>
                  ))}
                  {virt.end < tasks.length && <tr style={{ height: virt.total - virt.offset - (virt.end - virt.start) * rowH }}><td colSpan={7} style={{ padding: 0, border: 'none' }} /></tr>}
                </>
              )}
            </tbody>
          </table>
        </div>
        <div className="table-foot">
          <span className="mono">{tasks.length} rows</span>
          <span style={{ marginLeft: 'auto' }} className="mono">CSV · select to act</span>
        </div>
      </Card>

      <Collapsible title="Checks by type" storageKey="report-gates" compact meta={<span className="mono small muted" style={{ fontSize: 'var(--text-xs)' }}>{Object.keys(gates).length} types</span>}>
        <div className="gate-tiles">
          {Object.entries(gates).map(([gate, s]) => {
            const tot = s.pass + s.reject;
            const pr = tot ? (s.pass / tot) * 100 : 0;
            return (
              <div key={gate} className="gate-tile">
                <div className="section-head">
                  <span className="mono" style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--fg-1)' }}>{gate}</span>
                  <span className="mono" style={{ fontSize: 'var(--text-xs)' }}><span style={{ color: 'var(--green)', fontWeight: 700 }}>{s.pass}</span><span className="muted"> / </span><span style={{ color: s.reject ? 'var(--red)' : 'var(--fg-3)', fontWeight: 700 }}>{s.reject}</span></span>
                </div>
                <Progress value={pr} variant={s.reject ? 'warning' : 'success'} />
                <div className="mono small muted" style={{ fontSize: 'var(--text-2xs)' }}>{s.reject ? `${Math.round((s.reject / tot) * 100)}% rejected` : 'no rejections'} · {tot} events</div>
              </div>
            );
          })}
          {Object.keys(gates).length === 0 && <div className="small muted" style={{ padding: 'var(--space-3)', background: 'var(--bg-1)', border: '1px dashed var(--border)', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>No check results yet — chat or run work to generate them</div>}
        </div>
      </Collapsible>

      <Collapsible
        title="Packages & safety"
        storageKey="report-sec"
        defaultOpen={false}
        compact
        meta={<span className="mono small muted" style={{ fontSize: 'var(--text-xs)' }}>{sbom?.count ?? 0} packages · {waivers.length} exceptions</span>}
      >
      <div className="sec-grid">
        <Card className="panel-pad">
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Packages — {sbom?.count ?? 0}</div>
          {sbom && sbom.packages.length > 0 ? (
            <div className="list-scroll">
              {sbom.packages.slice(0, 8).map((p) => (
                <div key={`${p.name}@${p.version}`} className="mono list-row">
                  <span>{p.name}</span><span className="muted">{p.version || 'unpinned'}</span>
                </div>
              ))}
              {sbom.count > 8 && <span className="small muted">+{sbom.count - 8} more</span>}
            </div>
          ) : (
            <div className="small muted">No package list yet</div>
          )}
        </Card>
        <Card className="panel-pad">
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Network safety</div>
          {sink ? (
            sink.clean ? <Badge variant="proven">clean</Badge> : <Badge variant="blocked">{sink.violations.length} issues</Badge>
          ) : (
            <span className="small muted">Loading…</span>
          )}
          {sink && sink.violations.length > 0 && (
            <div className="list-scroll" style={{ marginTop: 'var(--space-2)' }}>
              {(sink.violations as Array<{ kind: string; target: string; taint: string }>).slice(0, 3).map((v, i) => (
                <div key={i} className="mono" style={{ fontSize: 'var(--text-xs)', padding: '4px 8px', background: 'var(--red-bg)', border: '1px solid var(--red-border)', borderRadius: 'var(--radius-xs)', color: 'var(--red)' }}>{v.kind} → {v.target}</div>
              ))}
            </div>
          )}
        </Card>
        <Card className="panel-pad">
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Review tips</div>
          {checklist.length ? (
            <div className="col-stack">
              {checklist.slice(0, 6).map((c) => (
                <div key={c} className="field-block" style={{ fontSize: 'var(--text-sm)', padding: '6px 8px' }}>{c}</div>
              ))}
            </div>
          ) : (
            <span className="small muted">Tips appear after past review failures</span>
          )}
        </Card>
        <Card className="panel-pad">
          <div className="section-label" style={{ marginBottom: 'var(--space-2)' }}>Exceptions — {waivers.length} open</div>
          {waivers.length ? (
            <div className="list-scroll">
              {(waivers as Array<{ text?: string; expires?: string }>).slice(0, 4).map((w, i) => (
                <div key={i} className="mono" style={{ fontSize: 'var(--text-xs)', padding: '6px 8px', background: 'var(--yellow-bg)', border: '1px solid var(--yellow-border)', borderRadius: 'var(--radius-xs)', color: 'var(--yellow)' }}>{String((w as { text?: string }).text || JSON.stringify(w)).slice(0, 80)}{(w as { expires?: string }).expires ? ` → ${(w as { expires?: string }).expires}` : ''}</div>
              ))}
            </div>
          ) : (
            <Badge variant="proven">none open</Badge>
          )}
        </Card>
      </div>
      </Collapsible>

      {criticals.length > 0 && (
        <div id="report-criticals" key={critKey}>
        <Collapsible
          title={`Open problems — ${criticals.length}`}
          storageKey="report-criticals"
          compact
          defaultOpen
          badge={<Badge variant="blocked" style={{ fontSize: 'var(--text-2xs)' }}>{criticals.length}</Badge>}
          meta={<span className="mono small" style={{ color: 'var(--red)', fontSize: 'var(--text-xs)' }}>fix or approve an exception</span>}
          style={{ borderColor: 'var(--red-border)' }}
        >
          <div className="col-stack">
            {(criticals as Array<{ text?: string; layer?: string; message?: string; severity?: string }>).map((c, i) => (
              <div key={i} className="crit-row">
                <span className="crit-dot" aria-hidden />
                <span style={{ flex: 1, lineHeight: 'var(--leading-normal)' }}>{c.text || c.layer || c.message || JSON.stringify(c)}</span>
                <Badge variant="blocked" style={{ fontSize: 'var(--text-2xs)' }}>{c.severity || 'problem'}</Badge>
              </div>
            ))}
          </div>
        </Collapsible>
        </div>
      )}

      <div className="foot-meta">
        <span className="mono">SUPER v1.0</span>
        <span aria-hidden>·</span>
        <span>Log: <code style={{ fontSize: 'var(--text-2xs)' }}>.super/gate.log.jsonl</code></span>
      </div>
    </div>
  );
}
