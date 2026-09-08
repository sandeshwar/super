import { useState } from 'react';
import { api } from '../../api';
import type { ApprovalRequest } from '../../types';
import { userMessage } from '../../lib/errors';
import { Button } from '../ui/Button';

type Props = {
  approvals: ApprovalRequest[];
  onResolved?: (next: ApprovalRequest[]) => void;
};

export function ApprovalCards({ approvals, onResolved }: Props) {
  if (!approvals.length) return null;
  return (
    <div className="approval-stack" style={{ display: 'flex', flexDirection: 'column', gap: 8, margin: '8px 0' }}>
      {approvals.map((a) => (
        <ApprovalCard
          key={`${a.kind}-${a.id}`}
          approval={a}
          onChange={(updated) => {
            const next = approvals.map((x) => (x.kind === a.kind && x.id === a.id ? updated : x));
            onResolved?.(next);
          }}
        />
      ))}
    </div>
  );
}

function ApprovalCard({ approval, onChange }: { approval: ApprovalRequest; onChange: (a: ApprovalRequest) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const done = approval.status && approval.status !== 'pending';

  const act = async (action: 'approve' | 'reject' | 'confirm') => {
    setBusy(true);
    setErr(null);
    try {
      if (approval.kind === 'agent') {
        await api.approveAgent(String(approval.id));
        onChange({ ...approval, status: 'approved' });
      } else if (approval.kind === 'capability') {
        if (action === 'reject') {
          await api.rejectCapability(String(approval.id));
          onChange({ ...approval, status: 'rejected' });
        } else {
          await api.approveCapability(String(approval.id));
          onChange({ ...approval, status: 'approved' });
        }
      } else if (approval.kind === 'memory') {
        await api.confirmMemory(Number(approval.id));
        onChange({ ...approval, status: 'confirmed' });
      }
    } catch (e) {
      setErr(userMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const kindLabel =
    approval.kind === 'agent' ? 'Agent' :
    approval.kind === 'capability' ? 'Capability' :
    approval.kind === 'memory' ? 'Memory' : approval.kind;

  return (
    <div
      className={`approval-card status-${approval.status || 'pending'}`}
      style={{
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-md)',
        background: done ? 'var(--bg-1)' : 'var(--accent-soft)',
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
      role="group"
      aria-label={`${kindLabel} approval`}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', letterSpacing: '0.04em' }}>
          NEEDS APPROVAL · {kindLabel.toUpperCase()}
        </span>
        {done && (
          <span className="mono" style={{ fontSize: 'var(--text-2xs)', color: 'var(--green)' }}>
            {String(approval.status).toUpperCase()}
          </span>
        )}
      </div>
      <div style={{ fontWeight: 600, color: 'var(--fg-0)' }}>{approval.title}</div>
      {approval.detail && (
        <div className="small" style={{ color: 'var(--fg-2)' }}>{approval.detail}</div>
      )}
      {err && <div className="small" style={{ color: 'var(--red)' }}>{err}</div>}
      {!done && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {approval.kind === 'capability' ? (
            <>
              <Button size="sm" variant="primary" disabled={busy} onClick={() => void act('approve')}>Approve</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act('reject')}>Reject</Button>
            </>
          ) : approval.kind === 'memory' ? (
            <Button size="sm" variant="primary" disabled={busy} onClick={() => void act('confirm')}>Confirm</Button>
          ) : (
            <Button size="sm" variant="primary" disabled={busy} onClick={() => void act('approve')}>Approve</Button>
          )}
        </div>
      )}
    </div>
  );
}
