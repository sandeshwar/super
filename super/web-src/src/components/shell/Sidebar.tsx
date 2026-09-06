import { api } from '../../api';
import type { TaskNode } from '../../types';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Collapsible } from '../ui/Collapsible';
import { Progress } from '../ui/Progress';
import { Icons } from '../ui/Icon';
import { Alert } from '../ui/Alert';
import { userMessage } from '../../lib/errors';
import { Link, type View } from '../../lib/router';
import type { Stats } from './hooks/useAppData';

const VIEW_META: Record<View, { title: string; desc: string; icon: keyof typeof Icons }> = {
  chat: { title: 'Chat', desc: 'Grounded assistant · every reply verified against repo symbols', icon: 'chat' },
  tree: { title: 'Job Tree', desc: 'DAG of microtasks · leaf-only model, proven in order', icon: 'tree' },
  approve: { title: 'Approve', desc: 'Human-in-loop gate · fatigue-aware, critic-backed', icon: 'approve' },
  report: { title: 'Report Card', desc: 'Provenance ledger · gates, catch rates & criticals', icon: 'report' },
};

type Props = {
  view: View;
  tasks: TaskNode[];
  gates: Record<string, { pass: number; reject: number }>;
  criticals: unknown[];
  stats: Stats;
  workspace: string;
  onWorkspaceChange: (v: string) => void;
  reloadFlash: boolean;
  setReloadFlash: (v: boolean) => void;
  error: string | null;
  setError: (v: string | null) => void;
  offlinePending: number;
  mobileNav: boolean;
  refresh: () => void;
};

export function Sidebar({ view, tasks, gates, criticals, stats, workspace, onWorkspaceChange, reloadFlash, setReloadFlash, error, setError, offlinePending, mobileNav, refresh }: Props) {
  return (
    <aside className={`app-sidebar ${mobileNav ? 'open' : ''}`} aria-label="Sidebar">
      <div className="sidebar-top">
        <div className="brand">
          <div className="brand-mark" aria-hidden>S</div>
          <div className="brand-wordmark">SUPER<span>Gated harness</span></div>
          <span className="brand-version">v1.0</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <div className="nav-section">
          <div className="nav-label">Workspace <span className="mono muted" style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>⌘K</span></div>
          {(['chat', 'tree', 'approve', 'report'] as View[]).map((v) => {
            const Icon = Icons[v];
            const count = v === 'tree' ? tasks.length : v === 'approve' ? stats.pending : v === 'report' ? stats.proven : undefined;
            const isActive = view === v;
            return (
              <Link
                key={v}
                to={{ view: v }}
                className={`nav-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon size={16} />
                <span style={{ flex: 1, textAlign: 'left' }}>{VIEW_META[v].title}</span>
                {v === 'approve' && stats.pending > 0 && !isActive && (
                  <Badge variant="warning" style={{ fontSize: 'var(--text-xs)' }}>{stats.pending}</Badge>
                )}
                {count !== undefined && count > 0 && !(v === 'approve' && stats.pending > 0 && !isActive) && (
                  <span className="badge-count">{v === 'report' ? `${stats.proven}/${stats.total}` : count}</span>
                )}
                {v === 'chat' && isActive && <span className="dot-live" style={{ background: 'var(--accent)' }} aria-hidden />}
              </Link>
            );
          })}
        </div>

        <div className="nav-section">
          <Collapsible
            title="Workspace"
            className="collapsible-bare"
            storageKey="side-workspace"
            meta={reloadFlash ? <span className="badge accent" style={{ fontSize: 9, padding: '1px 5px' }}>hot</span> : undefined}
          >
          <div style={{ display: 'flex', gap: 4, padding: '0 2px' }}>
            <input
              value={workspace}
              onChange={(e) => onWorkspaceChange(e.target.value)}
              placeholder="/path/to/workspace"
              aria-label="Workspace path"
              style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', padding: '5px 8px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)', fontFamily: 'var(--font-mono)' }}
              onKeyDown={async (e) => {
                if (e.key === 'Enter') {
                  try { await api.setWorkspace(workspace); setReloadFlash(true); setTimeout(() => setReloadFlash(false), 1500); void refresh(); } catch (err) { setError(userMessage(err)); }
                }
              }}
            />
            <button
              className="btn btn-sm"
              onClick={async () => {
                try { await api.setWorkspace(workspace); setReloadFlash(true); setTimeout(() => setReloadFlash(false), 1500); void refresh(); } catch (err) { setError(userMessage(err)); }
              }}
              aria-label="Set workspace"
            >
              set
            </button>
          </div>
          <div className="small muted" style={{ padding: '4px 8px', fontSize: 'var(--text-2xs)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={workspace}>{workspace ? workspace.split('/').slice(-2).join('/') : '— no workspace'}</div>
          </Collapsible>
        </div>

        <div className="nav-section">
          <Collapsible
            title="Health"
            className="collapsible-bare"
            storageKey="side-health"
            meta={<span className="mono" style={{ fontSize: 'var(--text-2xs)' }}>{stats.gatePass}/{stats.gateReject} rej</span>}
          >
          <Card style={{ padding: 'var(--space-2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span className="small muted" style={{ fontWeight: 600, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)' }}>GATES</span>
              <span className="mono small" style={{ fontSize: 'var(--text-xs)' }}>{stats.gatePass} <span className="muted">/</span> <span style={{ color: stats.gateReject ? 'var(--red)' : 'var(--fg-2)' }}>{stats.gateReject} rej</span></span>
            </div>
            <div style={{ marginTop: 'var(--space-2)' }}>
              <Progress value={stats.gatePass} max={stats.gatePass + stats.gateReject || 1} />
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
              {Object.entries(gates).slice(0, 4).map(([k, s]) => (
                <span key={k} className="mono" style={{ fontSize: 'var(--text-2xs)', padding: '2px var(--space-2)', borderRadius: 'var(--radius-xs)', background: 'var(--bg-3)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>{k} {s.pass}:{s.reject}</span>
              ))}
              {Object.keys(gates).length === 0 && <span className="small muted">No gate events yet</span>}
            </div>
          </Card>
          </Collapsible>
        </div>
      </nav>

      <div className="sidebar-bottom">
        <Card style={{ padding: 'var(--space-2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-2)' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="k">Provenance</div>
            <div className="v">{stats.proven} <span className="muted" style={{ fontWeight: 400 }}>/ {stats.total || '—'}</span></div>
            <div className="proven-bar"><i style={{ width: `${stats.pct}%` }} /></div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div className="mono" style={{ fontSize: 'var(--text-md)', fontWeight: 700, lineHeight: 1, color: stats.pct === 100 ? 'var(--green)' : 'var(--fg-0)' }}>{stats.pct}<span style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, color: 'var(--fg-3)' }}>%</span></div>
            <div className="small muted" style={{ fontSize: 'var(--text-2xs)', marginTop: 'var(--space-1)' }}>{criticals.length ? `${criticals.length} critical` : 'All clear'}</div>
          </div>
        </Card>
        <div className="sidebar-meta">
          <span className="dot" aria-hidden />
          <span>Local · 127.0.0.1:4311</span>
          <span style={{ marginLeft: 'auto' }} className="mono">{stats.total} jobs</span>
        </div>
        {offlinePending > 0 && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{offlinePending} queued (offline) — auto-retrying</Alert>}
        {error && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{error}</Alert>}
      </div>
    </aside>
  );
}
