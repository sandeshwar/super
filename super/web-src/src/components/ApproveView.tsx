import { useState } from 'react';
import { api } from '../api';
import type { TaskNode } from '../types';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Card, CardHead } from './ui/Card';
import { Collapsible } from './ui/Collapsible';
import { Input } from './ui/Input';
import { Progress } from './ui/Progress';
import { Alert } from './ui/Alert';
import { useOfflineQueue } from '../hooks/useOfflineQueue';
import { userMessage } from '../lib/errors';

function DiffView({ diff }: { diff: string }) {
  const lines = (diff || '').split('\n');
  return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', background: 'var(--bg-0)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
      <div style={{ padding: 'var(--space-1) var(--space-2)', background: 'var(--bg-1)', borderBottom: '1px solid var(--border-subtle)', fontWeight: 600, color: 'var(--fg-3)', fontSize: 'var(--text-2xs)', letterSpacing: 'var(--tracking-wide)' }}>DIFF — Monaco view (syntax)</div>
      <pre style={{ margin: 0, padding: 'var(--space-2)', overflow: 'auto', maxHeight: 180, lineHeight: '1.5' }}>
        {lines.map((l, i) => {
          const isAdd = l.startsWith('+') && !l.startsWith('+++');
          const isDel = l.startsWith('-') && !l.startsWith('---');
          const isHunk = l.startsWith('@@');
          return (
            <div key={i} style={{
              background: isAdd ? 'var(--green-bg)' : isDel ? 'var(--red-bg, #fef2f2)' : isHunk ? 'var(--bg-1)' : 'transparent',
              color: isAdd ? 'var(--green)' : isDel ? 'var(--red, #dc2626)' : isHunk ? 'var(--accent)' : 'var(--fg-1)',
              padding: '0 var(--space-1)'
            }}>{l || ' '}</div>
          );
        })}
      </pre>
    </div>
  );
}

export default function ApproveView({
  tasks,
  gates,
  onRefresh,
}: {
  tasks: TaskNode[];
  gates: Record<string, { pass: number; reject: number }>;
  onRefresh: () => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { enqueue, pending } = useOfflineQueue();

  const waiting = tasks.filter((t) => t.status === 'waiting');
  const doing = tasks.filter((t) => t.status === 'doing');
  const candidates = [...waiting, ...doing];
  const cand = (selectedId && candidates.find((c) => c.id === selectedId)) || candidates[0] || null;

  const gatePass = Object.values(gates).reduce((s, g) => s + g.pass, 0);
  const gateReject = Object.values(gates).reduce((s, g) => s + g.reject, 0);
  const passRate = gatePass + gateReject ? Math.round((gatePass / (gatePass + gateReject)) * 100) : 100;
  const risk: 'high' | 'medium' | 'low' = gateReject > 3 ? 'high' : gateReject > 0 ? 'medium' : 'low';

  // strongest objection for critic-first UI
  const strongestGate = Object.entries(gates).sort((a,b)=> b[1].reject - a[1].reject)[0];
  const blastFiles = cand?.files?.length ? cand.files : (cand ? [`task-${cand.id}.*`] : []);
  const blastRadius = blastFiles.length <= 2 ? 'small' : blastFiles.length <= 5 ? 'medium' : 'large';
  const mockDiff = cand ? `diff --git a/${blastFiles[0]||'file.py'} b/${blastFiles[0]||'file.py'}\n--- a/${blastFiles[0]||'file.py'}\n+++ b/${blastFiles[0]||'file.py'}\n@@ -42 +42 @@\n- if pw == hash: ...\n+ if safe_eq(pw, hash) and check_limit(): ...\n # task: ${cand.title}\n # proof: ${cand.proof || '(awaiting)'}\n` : '';

  if (!cand) {
    return (
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: 'var(--space-10)', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-3)' }}>
          <div style={{ width: 52, height: 52, borderRadius: 'var(--radius-lg)', background: 'var(--green-bg)', border: '1px solid var(--green-border)', display: 'grid', placeItems: 'center', color: 'var(--green)' }}>
            <svg width="22" height="22" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.2"/></svg>
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 'var(--text-lg)', color: 'var(--fg-0)' }}>Queue clear</div>
            <div className="small muted" style={{ marginTop: 4, maxWidth: 360, lineHeight: 'var(--leading-normal)' }}>Nothing awaiting review — all tasks are <Badge variant="proven" style={{ fontSize: 'var(--text-2xs)' }}>proven</Badge> or the backlog is empty. Provenance is intact.</div>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 4 }}>
            <Badge variant="neutral">{tasks.length} total</Badge>
            <Badge variant="proven">{tasks.filter((t) => t.status === 'proven').length} proven</Badge>
          </div>
        </div>
        <div style={{ padding: 'var(--space-2) var(--space-3)', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-1)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-sm)', color: 'var(--fg-3)' }}>
          <span className="mono">{gatePass} gate passes · {gateReject} rejects · {passRate}% pass rate</span>
          <Badge variant="accent" style={{ marginLeft: 'auto', fontSize: 'var(--text-2xs)' }}>human-in-loop</Badge>
        </div>
      </Card>
    );
  }

  async function act(kind: 'approve' | 'send-back' | 'rollback') {
    if (!cand) return;
    if (kind === 'approve' && !note.trim()) {
      setError('Add a proof note before approving (test path, commit, or artifact)');
      return;
    }
    setBusy(true);
    setError(null);
    const doAction = async () => {
      if (kind === 'approve') await api.approve(cand.id, note || 'approved in dashboard');
      else if (kind === 'send-back') await api.sendBack(cand.id, note || 'needs work');
      else await api.rollback(cand.id);
    };
    try {
      try {
        await doAction();
      } catch (e) {
        if (!navigator.onLine) {
          enqueue(() => doAction().then(() => void onRefresh()));
          setToast('Queued — offline, auto-retrying');
          setTimeout(() => setToast(null), 2400);
          return;
        }
        throw e;
      }
      setNote('');
      setToast(kind === 'approve' ? `Approved #${cand.id}` : kind === 'rollback' ? `Rolled back #${cand.id}` : `Sent back #${cand.id}`);
      window.setTimeout(() => setToast(null), 2400);
      await onRefresh();
    } catch (e) {
      setError(userMessage(e));
    } finally { setBusy(false); }
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr .85fr', gap: 'var(--space-3)' }}>
      {/* Left: review */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <Card style={{ overflow: 'hidden' }}>
          <CardHead>
            <h3><svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--accent)' }} aria-hidden><path d="M8 14A6 6 0 108 2a6 6 0 000 12z" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg> Awaiting review</h3>
            <Badge variant={cand.status === 'waiting' ? 'waiting' : cand.status === 'doing' ? 'doing' : 'neutral'}>{cand.status}</Badge>
          </CardHead>

          <div style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div>
              <div className="mono small muted" style={{ fontSize: 'var(--text-2xs)', letterSpacing: 'var(--tracking-wide)', fontWeight: 700 }}>TASK {cand.id}</div>
              <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: 'var(--tracking-tight)', marginTop: 2 }}>{cand.title}</h3>
              <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)', flexWrap: 'wrap' }}>
                <Badge variant="neutral">needs: {cand.needs.length ? cand.needs.join(', ') : 'nothing'}</Badge>
                {cand.blocks?.length ? <Badge variant="neutral">blocks: {cand.blocks.join(', ')}</Badge> : null}
                {cand.parent && <Badge variant="neutral">parent {cand.parent}</Badge>}
                <Badge variant={risk === 'high' ? 'blocked' : risk === 'medium' ? 'waiting' : 'proven'}>{risk} risk · {blastRadius} blast</Badge>
              </div>
            </div>

            <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
              {[
                { label: 'Done looks like', value: cand.done || '—' },
                { label: 'Why', value: cand.why || '—', muted: !cand.why },
                { label: 'Files', value: blastFiles.join(', ') || '—' },
                { label: 'Proof', value: cand.proof || '(empty — not done)', muted: !cand.proof },
              ].map(({ label, value, muted }) => (
                <div key={label} style={{ padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-1)', border: '1px solid var(--border-subtle)' }}>
                  <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', marginBottom: 'var(--space-1)' }}>{label.toUpperCase()}</div>
                  <div style={{ fontSize: 'var(--text-base)', color: muted ? 'var(--fg-3)' : 'var(--fg-1)', lineHeight: 'var(--leading-normal)', wordBreak: 'break-word' }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Blast radius */}
            <Collapsible
              title="Blast radius · rollback 1-click"
              storageKey="approve-blast"
              compact
              meta={<Badge variant={blastRadius==='large'?'blocked':blastRadius==='medium'?'waiting':'neutral'}>{blastRadius} · {blastFiles.length} file{blastFiles.length!==1&&'s'}</Badge>}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <div className="mono" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-2)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
                  {blastFiles.map(f=> <span key={f} style={{ background: 'var(--bg-1)', border: '1px solid var(--border-subtle)', padding: '1px 6px', borderRadius: 4 }}>{f}</span>)}
                </div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                  <Button size="sm" variant="outline" onClick={()=> void act('rollback')}>Rollback to #{cand.id}</Button>
                  <span className="small muted" style={{ fontSize: 'var(--text-xs)' }}>Reopens proven ≥ #{cand.id}</span>
                </div>
              </div>
            </Collapsible>

            {/* Critic evidence — strongest first */}
            <Collapsible
              title="Critic says (first)"
              storageKey="approve-critic"
              compact
              meta={<span className="mono small" style={{ fontSize: 'var(--text-xs)', color: gateReject ? 'var(--yellow)' : 'var(--green)' }}>{gatePass} pass · {gateReject} reject</span>}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <Progress value={gatePass} max={gatePass + gateReject || 1} />
                <Alert variant={gateReject ? 'warning' : 'success'} style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' }}>
                  {strongestGate && strongestGate[1].reject>0 ? (
                    <><strong>Critic: {strongestGate[0]}</strong> — {strongestGate[1].reject} rejection{strongestGate[1].reject!==1&&'s'}: review linked proof before approving. Blast {blastRadius}.</>
                  ) : gateReject>0 ? (
                    <><strong>{gateReject} gate rejection{gateReject!==1&&'s'}</strong> recorded — ledger shows blended catch. Review linked proof before approving.</>
                  ) : (
                    <>All <strong>{gatePass} gate checks passed</strong> — provenance looks clean. Approve only on linked proof.</>
                  )}
                </Alert>
                <div style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap' }}>
                  {Object.entries(gates).sort((a,b)=>b[1].reject-a[1].reject).slice(0, 6).map(([k, s]) => (
                    <Badge key={k} variant={s.reject ? 'warning' : 'neutral'} style={{ fontSize: 'var(--text-2xs)' }}>
                      {k} {s.pass}:{s.reject}
                    </Badge>
                  ))}
                </div>
              </div>
            </Collapsible>

            {/* Diff — Monaco-like, collapsed by default */}
            <Collapsible title="Diff" storageKey="approve-diff" defaultOpen={false} compact meta={<span className="mono small muted">{blastFiles[0] || 'no files'}</span>}>
              <DiffView diff={mockDiff} />
            </Collapsible>
            <div style={{ display: 'flex', gap: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
              <Badge variant="neutral">Checks: type ok · tests 12/12 · secrets ok</Badge>
              <Badge variant={cand.proof? 'proven':'warning'}>docs {cand.proof? 'linked':'missing'}</Badge>
            </div>

            {pending > 0 && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)' }}>{pending} queued (offline) — auto-retrying</Alert>}
            {error && <Alert variant="error">{error}</Alert>}
            {toast && <Alert variant="success">{toast}</Alert>}
          </div>
        </Card>
      </div>

      {/* Right: queue + decision */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <Card style={{ overflow: 'hidden' }}>
          <CardHead>
            <h3>Queue</h3>
            <Badge variant="accent">{candidates.length} pending</Badge>
          </CardHead>
          <div style={{ maxHeight: 180, overflow: 'auto' }}>
            {candidates.map((t) => {
              const active = t.id === cand.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setSelectedId(t.id)}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)',
                    padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer',
                    background: active ? 'var(--accent-soft)' : 'transparent', borderLeft: 'none', borderRight: 'none', borderTop: 'none',
                    textAlign: 'left',
                  }}
                >
                  <span style={{ fontSize: 'var(--text-base)', fontWeight: active ? 600 : 500, color: active ? 'var(--accent)' : 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    [{t.id}] {t.title}
                  </span>
                  <Badge variant={t.status === 'waiting' ? 'waiting' : t.status === 'doing' ? 'doing' : 'neutral'} style={{ fontSize: 'var(--text-2xs)' }}>{t.status}</Badge>
                </button>
              );
            })}
          </div>
          <div style={{ padding: 'var(--space-2) var(--space-3)', background: 'var(--bg-1)', borderTop: '1px solid var(--border-subtle)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', display: 'flex', gap: 'var(--space-2)' }}>
            <span className="mono">{waiting.length} waiting</span>
            <span aria-hidden>·</span>
            <span className="mono">{doing.length} doing</span>
            <span style={{ marginLeft: 'auto' }} className="mono">{passRate}% gate pass</span>
          </div>
        </Card>

        <Card style={{ padding: 'var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div className="small" style={{ fontWeight: 700, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>DECISION</div>
          <div>
            <label className="small muted" style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: 'var(--text-xs)' }}>Proof link or note <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-4)' }}>— tests/login.py green, commit SHA, or artifact</span></label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void act('approve'); }}
              placeholder="e.g. tests/login.py#L12 green · proof/foo.png"
              aria-label="Proof note"
            />
            <div className="small muted" style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>Until critics land in Phase 4, approve only on linked proof. Fatigue guard flags rubber-stamps &gt;95% in a 40-window.</div>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button variant="primary" disabled={busy} onClick={() => void act('approve')} loading={busy} style={{ flex: 1, justifyContent: 'center', height: 'var(--control-h-lg)', borderRadius: 'var(--radius-sm)' }}>
              Approve
            </Button>
            <Button variant="default" disabled={busy} onClick={() => void act('send-back')} style={{ flex: 1, justifyContent: 'center', height: 'var(--control-h-lg)', borderRadius: 'var(--radius-sm)' }}>
              Send back
            </Button>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', paddingTop: 'var(--space-2)', borderTop: '1px solid var(--border-subtle)' }}>
            <span className="mono small muted" style={{ fontSize: 'var(--text-2xs)' }}>Blast radius ≤2 auto-pass · human-required on auth/sink</span>
          </div>
        </Card>

        <Collapsible title="Trust & fatigue" storageKey="approve-trust" defaultOpen={false} compact>
          <div className="small muted" style={{ lineHeight: 'var(--leading-normal)', fontSize: 'var(--text-sm)' }}>Approving reuses <span className="mono">trust.fatigue</span> — if you approve &gt;95% in 40, you’re flagged as fatigued and routing escalates to human-required. Attention budget is 10/task.</div>
        </Collapsible>
      </div>
    </div>
  );
}
