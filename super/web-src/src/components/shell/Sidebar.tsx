import { api } from '../../api';
import type { TaskNode } from '../../types';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Collapsible } from '../ui/Collapsible';
import { Progress } from '../ui/Progress';
import { Icons } from '../ui/Icon';
import { Alert } from '../ui/Alert';
import { userMessage } from '../../lib/errors';
import { VIEW_META } from '../../lib/labels';
import { Link, type View } from '../../lib/router';
import type { Stats } from './hooks/useAppData';

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
  onOpenProblems?: () => void;
};

export function Sidebar({
  view, tasks, gates, criticals, stats, workspace, onWorkspaceChange, reloadFlash, setReloadFlash,
  error, setError, offlinePending, mobileNav, refresh, onOpenProblems,
}: Props) {
  const applyWorkspace = async (path: string) => {
    try {
      await api.setWorkspace(path);
      onWorkspaceChange(path);
      setReloadFlash(true);
      setTimeout(() => setReloadFlash(false), 1500);
      void refresh();
    } catch (err) {
      setError(userMessage(err));
    }
  };

  const browse = async () => {
    try {
      const res = await api.pickFolder(workspace || undefined);
      if (res.cancelled || !res.path) return;
      onWorkspaceChange(res.path);
      await applyWorkspace(res.path);
    } catch (err) {
      setError(userMessage(err));
    }
  };

  return (
    <aside id="app-sidebar" className={`app-sidebar ${mobileNav ? 'open' : ''}`} aria-label="Sidebar">
      <div className="sidebar-top">
        <div className="brand">
          <div className="brand-mark" aria-hidden>S</div>
          <div className="brand-wordmark">SUPER<span>Generalist assistant</span></div>
          <span className="brand-version">v1.0</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        <div className="nav-section">
          <div className="nav-label">Pages <span className="mono muted" style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>⌘K</span></div>
          {(['chat', 'tree', 'approve', 'report'] as View[]).map((v) => {
            const Icon = Icons[VIEW_META[v].icon];
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
          <div className="nav-label">System</div>
          <Link
            to={{ view: 'settings' }}
            className={`nav-item ${view === 'settings' ? 'active' : ''}`}
            aria-current={view === 'settings' ? 'page' : undefined}
          >
            <Icons.settings size={16} />
            <span style={{ flex: 1, textAlign: 'left' }}>{VIEW_META.settings.title}</span>
          </Link>
        </div>

        <div className="nav-section">
          <Collapsible
            title="Working dir"
            className="collapsible-bare"
            storageKey="side-workspace"
            meta={reloadFlash ? <span className="badge accent" style={{ fontSize: 9, padding: '1px 5px' }}>updated</span> : undefined}
          >
            <div style={{ display: 'flex', gap: 4, padding: '0 2px' }}>
              <input
                value={workspace}
                onChange={(e) => onWorkspaceChange(e.target.value)}
                placeholder="/path/to/project"
                aria-label="Working directory"
                style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-xs)', padding: '5px 8px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)', fontFamily: 'var(--font-mono)' }}
                onKeyDown={async (e) => {
                  if (e.key === 'Enter') await applyWorkspace(workspace);
                }}
              />
              <button
                className="btn btn-sm"
                type="button"
                onClick={() => void browse()}
                aria-label="Browse for folder"
                title="Browse"
              >
                Browse…
              </button>
              <button
                className="btn btn-sm"
                type="button"
                onClick={() => void applyWorkspace(workspace)}
                aria-label="Set working directory"
              >
                set
              </button>
            </div>
            <div className="small muted" style={{ padding: '4px 8px', fontSize: 'var(--text-2xs)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={workspace}>
              {workspace ? workspace.split('/').slice(-2).join('/') : '— no folder'}
            </div>
          </Collapsible>
        </div>

        <div className="nav-section">
          <Collapsible
            title="Checks"
            className="collapsible-bare"
            storageKey="side-health"
            meta={<span className="mono" style={{ fontSize: 'var(--text-2xs)' }}>{stats.gatePass} ok · {stats.gateReject} failed</span>}
          >
            <Card style={{ padding: 'var(--space-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="small muted" style={{ fontWeight: 600, letterSpacing: 'var(--tracking-wide)', fontSize: 'var(--text-2xs)' }}>CHECKS</span>
                <span className="mono small" style={{ fontSize: 'var(--text-xs)' }}>
                  {stats.gatePass} <span className="muted">/</span>{' '}
                  <span style={{ color: stats.gateReject ? 'var(--red)' : 'var(--fg-2)' }}>{stats.gateReject} failed</span>
                </span>
              </div>
              <div style={{ marginTop: 'var(--space-2)' }}>
                <Progress value={stats.gatePass} max={stats.gatePass + stats.gateReject || 1} />
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
                {Object.entries(gates).slice(0, 4).map(([k, s]) => (
                  <span key={k} className="mono" style={{ fontSize: 'var(--text-2xs)', padding: '2px var(--space-2)', borderRadius: 'var(--radius-xs)', background: 'var(--bg-3)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>{k} {s.pass}:{s.reject}</span>
                ))}
                {Object.keys(gates).length === 0 && <span className="small muted">No checks yet</span>}
              </div>
            </Card>
          </Collapsible>
        </div>
      </nav>

      <div className="sidebar-bottom">
        <Card className="proven-card">
          <div className="proven-card-row">
            <div className="proven-card-main">
              <div className="k">Done</div>
              <div className="v">{stats.proven} <span className="muted" style={{ fontWeight: 400 }}>/ {stats.total || '—'}</span></div>
            </div>
            <button
              type="button"
              className="proven-card-side"
              onClick={onOpenProblems}
              disabled={!criticals.length}
              title={criticals.length ? 'View open problems' : undefined}
            >
              <div className="proven-pct" style={{ color: stats.pct === 100 ? 'var(--green)' : undefined }}>
                {stats.pct}<span className="proven-pct-unit">%</span>
              </div>
              <div className="proven-side-meta" style={{ color: criticals.length ? 'var(--red)' : undefined }}>
                {criticals.length ? `${criticals.length} problem${criticals.length !== 1 ? 's' : ''}` : 'All clear'}
              </div>
            </button>
          </div>
          <div className="proven-bar"><i style={{ width: `${stats.pct}%` }} /></div>
        </Card>
        <div className="sidebar-meta">
          <span className="dot" aria-hidden />
          <span>Local only</span>
          <span style={{ marginLeft: 'auto' }} className="mono">{stats.total} tasks</span>
        </div>
        {offlinePending > 0 && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{offlinePending} action{offlinePending !== 1 && 's'} waiting to retry</Alert>}
        {error && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{error}</Alert>}
      </div>
    </aside>
  );
}
