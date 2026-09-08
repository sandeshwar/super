import { useEffect, useRef, useState } from 'react';
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
import { statusLabel } from '../lib/labels';
import { navigate } from '../lib/router';

function DiffUnavailable({ files }: { files: string[] }) {
  return (
    <div className="diff-unavailable">
      <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', marginBottom: files.length ? 'var(--space-2)' : 0 }}>
        No git diff for this task yet. Approve only if you have real proof (test output, commit, or screenshot).
      </Alert>
      {files.length > 0 && (
        <div className="mono chip-row" style={{ color: 'var(--fg-2)' }}>
          {files.map((f) => (
            <span key={f} className="file-chip">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function TaskDiff({ taskId, files }: { taskId: string; files: string[] }) {
  const [diff, setDiff] = useState<string | null>(null);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void api.diff({ id: taskId, paths: files }).then((r) => {
      if (cancelled) return;
      setDiff(r.diff || '');
      setEmpty(Boolean(r.empty) || !(r.diff || '').trim());
      setError(r.ok ? null : (r.error || 'diff failed'));
      setLoading(false);
    }).catch((e) => {
      if (cancelled) return;
      setError(userMessage(e));
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [taskId, files.join('\0')]);

  if (loading) {
    return <div className="small muted panel-pad">Loading git diff…</div>;
  }
  if (error) {
    return <DiffUnavailable files={files} />;
  }
  if (empty || !(diff || '').trim()) {
    return <DiffUnavailable files={files} />;
  }
  return (
    <pre className="mono diff-pre">
      {diff}
    </pre>
  );
}

export default function ApproveView({
  tasks,
  gates,
  onRefresh,
  taskId = null,
  onTaskIdChange,
}: {
  tasks: TaskNode[];
  gates: Record<string, { pass: number; reject: number }>;
  onRefresh: () => void;
  taskId?: string | null;
  onTaskIdChange?: (id: string | null) => void;
}) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [decisionFlash, setDecisionFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { enqueue, pending } = useOfflineQueue();
  const flashTimer = useRef<number | null>(null);
  const toastTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (flashTimer.current) window.clearTimeout(flashTimer.current);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
  }, []);

  const pulseFlash = () => {
    setDecisionFlash(true);
    if (flashTimer.current) window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setDecisionFlash(false), 900);
  };
  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 2400);
  };

  const waiting = tasks.filter((t) => t.status === 'waiting');
  const doing = tasks.filter((t) => t.status === 'doing');
  const candidates = [...waiting, ...doing];
  const cand = (taskId && candidates.find((c) => c.id === taskId)) || candidates[0] || null;
  const setSelectedId = (id: string) => onTaskIdChange?.(id);

  useEffect(() => {
    if (cand && cand.id !== taskId) onTaskIdChange?.(cand.id);
  }, [cand, taskId, onTaskIdChange]);

  const gatePass = Object.values(gates).reduce((s, g) => s + g.pass, 0);
  const gateReject = Object.values(gates).reduce((s, g) => s + g.reject, 0);
  const passRate = gatePass + gateReject ? Math.round((gatePass / (gatePass + gateReject)) * 100) : 100;
  const files = cand?.files?.length ? cand.files : [];
  const fileBlast = files.length;
  const unmetDeps = (cand?.needs || []).length;
  const risk: 'high' | 'medium' | 'low' =
    fileBlast >= 8 || unmetDeps >= 3 ? 'high'
      : fileBlast >= 3 || unmetDeps >= 1 || !(cand?.proof) ? 'medium'
        : 'low';

  const strongestGate = Object.entries(gates).sort((a, b) => b[1].reject - a[1].reject)[0];
  const fileScope = files.length === 0 ? 'no files listed' : files.length <= 2 ? 'few files' : files.length <= 5 ? 'several files' : 'many files';
  const canApprove = Boolean(note.trim());

  if (!cand) {
    return (
      <div className={`approve-shell${decisionFlash ? ' is-flash' : ''}`}>
        {toast && <Alert variant="success" className="alert--pop settings-alert">{toast}</Alert>}
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div className="approve-empty">
            <div className="approve-empty-icon">
              <svg width="22" height="22" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.2"/></svg>
            </div>
            <div>
              <div className="approve-empty-title">Nothing to review</div>
              <div className="small muted" style={{ marginTop: 4, maxWidth: 360, lineHeight: 'var(--leading-normal)' }}>
                All tasks are done, or there is no work queued yet.
              </div>
            </div>
            <div className="chip-row" style={{ marginTop: 4 }}>
              <Badge variant="neutral">{tasks.length} total</Badge>
              <Badge variant="proven">{tasks.filter((t) => t.status === 'proven').length} done</Badge>
            </div>
            <Button size="sm" variant="default" onClick={() => navigate({ view: 'tree' })}>Go to tasks</Button>
          </div>
          <div className="table-foot">
            <span className="mono">{gatePass} checks passed · {gateReject} failed · {passRate}% ok</span>
          </div>
        </Card>
      </div>
    );
  }

  async function act(kind: 'approve' | 'send-back' | 'rollback') {
    if (!cand) return;
    if (kind === 'approve' && !note.trim()) {
      setError('Add a proof note first — a test path, commit, or link to what you checked.');
      return;
    }
    setBusy(true);
    setError(null);
    const doAction = async () => {
      if (kind === 'approve') await api.approve(cand.id, note.trim());
      else if (kind === 'send-back') await api.sendBack(cand.id, note.trim() || 'needs more work');
      else await api.rollback(cand.id);
    };
    try {
      try {
        await doAction();
      } catch (e) {
        if (!navigator.onLine) {
          enqueue(() => doAction().then(() => void onRefresh()), `${kind} ${cand.id}`);
          showToast('Saved for later — will retry when you are back online');
          return;
        }
        throw e;
      }
      setNote('');
      showToast(kind === 'approve' ? `Marked #${cand.id} done` : kind === 'rollback' ? `Reopened from #${cand.id}` : `Sent #${cand.id} back`);
      if (kind === 'approve') pulseFlash();
      await onRefresh();
    } catch (e) {
      setError(userMessage(e));
    } finally { setBusy(false); }
  }

  return (
    <div className="split-approve">
      <div className="col-stack">
        <Card style={{ overflow: 'hidden' }}>
          <CardHead>
            <h3>Waiting for your review</h3>
            <Badge variant={cand.status === 'waiting' ? 'waiting' : cand.status === 'doing' ? 'doing' : 'neutral'}>{statusLabel(cand.status)}</Badge>
          </CardHead>

          <div className="panel-stack">
            <div>
              <div className="mono small muted" style={{ fontSize: 'var(--text-2xs)', letterSpacing: 'var(--tracking-wide)', fontWeight: 700 }}>TASK {cand.id}</div>
              <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: 'var(--tracking-tight)', marginTop: 2, fontFamily: 'var(--font-display)' }}>{cand.title}</h3>
              <div className="chip-row" style={{ marginTop: 'var(--space-2)' }}>
                <Badge variant="neutral">depends on: {cand.needs.length ? cand.needs.join(', ') : 'nothing'}</Badge>
                {cand.blocks?.length ? <Badge variant="neutral">blocks: {cand.blocks.join(', ')}</Badge> : null}
                {cand.parent && <Badge variant="neutral">under {cand.parent}</Badge>}
                <Badge variant={risk === 'high' ? 'blocked' : risk === 'medium' ? 'waiting' : 'proven'}>{risk} risk · {fileScope}</Badge>
              </div>
            </div>

            <div className="col-stack">
              {[
                { label: 'Done looks like', value: cand.done || '—' },
                { label: 'Why it matters', value: cand.why || '—', muted: !cand.why },
                { label: 'Files', value: files.length ? files.join(', ') : 'Not listed yet', muted: !files.length },
                { label: 'Proof so far', value: cand.proof || 'None yet — add your own below', muted: !cand.proof },
              ].map(({ label, value, muted }) => (
                <div key={label} className="field-block">
                  <div className="field-block-label">{label}</div>
                  <div className={`field-block-value${muted ? ' is-muted' : ''}`}>{value}</div>
                </div>
              ))}
            </div>

            <Collapsible
              title="Files this may change"
              storageKey="approve-blast"
              compact
              meta={<Badge variant={files.length > 5 ? 'blocked' : files.length > 2 ? 'waiting' : 'neutral'}>{files.length || 0} file{files.length !== 1 && 's'}</Badge>}
            >
              <div className="col-stack">
                {files.length ? (
                  <div className="mono chip-row" style={{ color: 'var(--fg-2)' }}>
                    {files.map((f) => <span key={f} className="file-chip">{f}</span>)}
                  </div>
                ) : (
                  <span className="small muted">No file list on this task yet.</span>
                )}
                <div className="toolbar-actions">
                  <Button size="sm" variant="outline" onClick={() => void act('rollback')}>Undo from #{cand.id}</Button>
                  <span className="small muted" style={{ fontSize: 'var(--text-xs)' }}>Reopens this task and anything after it</span>
                </div>
              </div>
            </Collapsible>

            <Collapsible
              title="Check results"
              storageKey="approve-critic"
              compact
              meta={<span className="mono small" style={{ fontSize: 'var(--text-xs)', color: gateReject ? 'var(--yellow)' : 'var(--green)' }}>{gatePass} ok · {gateReject} failed</span>}
            >
              <div className="col-stack">
                <Progress value={gatePass} max={gatePass + gateReject || 1} />
                <Alert variant={gateReject ? 'warning' : 'success'} style={{ fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' }}>
                  {strongestGate && strongestGate[1].reject > 0 ? (
                    <><strong>{strongestGate[0]}</strong> failed {strongestGate[1].reject} time{strongestGate[1].reject !== 1 && 's'}. Read the proof carefully before approving.</>
                  ) : gateReject > 0 ? (
                    <><strong>{gateReject} check{gateReject !== 1 && 's'} failed</strong> recently. Only approve if you have linked proof.</>
                  ) : (
                    <>All <strong>{gatePass} checks</strong> look clean so far. Still approve only with real proof.</>
                  )}
                </Alert>
                <div className="chip-row">
                  {Object.entries(gates).sort((a, b) => b[1].reject - a[1].reject).slice(0, 6).map(([k, s]) => (
                    <Badge key={k} variant={s.reject ? 'warning' : 'neutral'} style={{ fontSize: 'var(--text-2xs)' }}>
                      {k} {s.pass}:{s.reject}
                    </Badge>
                  ))}
                  {Object.keys(gates).length === 0 && <span className="small muted">No check history yet</span>}
                </div>
              </div>
            </Collapsible>

            <Collapsible title="Code changes" storageKey="approve-diff" defaultOpen compact meta={<span className="small muted">git diff</span>}>
              <TaskDiff taskId={cand.id} files={files} />
            </Collapsible>

            <div className="chip-row">
              <Badge variant={gateReject ? 'warning' : 'proven'}>
                Checks: {gatePass} ok · {gateReject} failed ({passRate}%)
              </Badge>
              <Badge variant={cand.proof ? 'proven' : 'warning'}>{cand.proof ? 'Has proof note' : 'No proof yet'}</Badge>
            </div>

            {pending > 0 && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)' }}>{pending} action{pending !== 1 && 's'} waiting to retry (offline)</Alert>}
            {error && <Alert variant="error">{error}</Alert>}
            {toast && <Alert variant="success" className="alert--pop">{toast}</Alert>}
          </div>
        </Card>
      </div>

      <div className="col-stack">
        <Card style={{ overflow: 'hidden' }}>
          <CardHead>
            <h3>Up next</h3>
            <Badge variant="accent">{candidates.length} waiting</Badge>
          </CardHead>
          <div style={{ maxHeight: 180, overflow: 'auto' }}>
            {candidates.map((t) => {
              const active = t.id === cand.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedId(t.id)}
                  className={`candidate-row${active ? ' is-active' : ''}`}
                >
                  <span className="candidate-row-title">[{t.id}] {t.title}</span>
                  <Badge variant={t.status === 'waiting' ? 'waiting' : t.status === 'doing' ? 'doing' : 'neutral'} style={{ fontSize: 'var(--text-2xs)' }}>{statusLabel(t.status)}</Badge>
                </button>
              );
            })}
          </div>
          <div className="table-foot">
            <span className="mono">{waiting.length} waiting</span>
            <span aria-hidden>·</span>
            <span className="mono">{doing.length} in progress</span>
            <span style={{ marginLeft: 'auto' }} className="mono">{passRate}% checks ok</span>
          </div>
        </Card>

        <Card className={`panel-stack-lg decision-card${decisionFlash ? ' is-flash' : ''}`}>
          <div className="section-label">Your decision</div>
          <div>
            <label className="small muted" style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: 'var(--text-xs)' }}>
              Proof note <span style={{ color: 'var(--fg-4)' }}>— required to approve (test path, commit, or link)</span>
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !busy && canApprove) void act('approve'); }}
              placeholder="e.g. tests/login.py passed · commit abc123"
              aria-label="Proof note"
            />
            <div className="small muted" style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' }}>
              Only mark done when you can point to what you verified. Approving without proof is blocked.
            </div>
          </div>
          <div className="decision-actions">
            <Button variant="primary" disabled={busy || !canApprove} onClick={() => void act('approve')} loading={busy}>
              Mark done
            </Button>
            <Button variant="default" disabled={busy} onClick={() => void act('send-back')}>
              Send back
            </Button>
          </div>
        </Card>

        <Collapsible title="About careful review" storageKey="approve-trust" defaultOpen={false} compact>
          <div className="small muted" style={{ lineHeight: 'var(--leading-normal)', fontSize: 'var(--text-sm)' }}>
            If you approve almost everything without reading, the system will start requiring stricter human review.
          </div>
        </Collapsible>
      </div>
    </div>
  );
}
