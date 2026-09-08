import { api } from '../../api';
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
  collapsed: boolean;
  onToggleCollapsed: () => void;
  refresh: () => void;
};

export function Sidebar({
  view, gates, criticals, stats, workspace, onWorkspaceChange, reloadFlash, setReloadFlash,
  error, setError, offlinePending, mobileNav, collapsed, onToggleCollapsed, refresh,
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
    <aside
      id="app-sidebar"
      className={`app-sidebar ${mobileNav ? 'open' : ''} ${collapsed ? 'is-collapsed' : ''}`}
      aria-label="Sidebar"
      aria-expanded={!collapsed}
    >
      <div className="sidebar-top">
        <button
          type="button"
          className="icon-btn sidebar-hamburger"
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          onClick={onToggleCollapsed}
          title={collapsed ? 'Expand nav' : 'Collapse nav'}
        >
          <Icons.menu size={16} />
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        <div className="nav-section">
          <div className="nav-label">Pages <span className="mono muted" style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>⌘K</span></div>
          {(['chat'] as View[]).map((v) => {
            const Icon = Icons[VIEW_META[v].icon];
            const isActive = view === v;
            return (
              <Link
                key={v}
                to={{ view: v }}
                className={`nav-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                title={VIEW_META[v].title}
              >
                <Icon size={16} />
                <span className="nav-item-label" style={{ flex: 1, textAlign: 'left' }}>{VIEW_META[v].title}</span>
                {v === 'chat' && isActive && <span className="dot-live" aria-hidden />}
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
            title={VIEW_META.settings.title}
          >
            <Icons.settings size={16} />
            <span className="nav-item-label" style={{ flex: 1, textAlign: 'left' }}>{VIEW_META.settings.title}</span>
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
              {criticals.length > 0 && (
                <div className="small" style={{ marginTop: 'var(--space-2)', color: 'var(--red)' }}>
                  {criticals.length} open problem{criticals.length !== 1 ? 's' : ''}
                </div>
              )}
            </Card>
          </Collapsible>
        </div>
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-meta">
          <span className="dot" aria-hidden />
          <span>Local only</span>
        </div>
        {offlinePending > 0 && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{offlinePending} action{offlinePending !== 1 && 's'} waiting to retry</Alert>}
        {error && <Alert variant="warning" style={{ fontSize: 'var(--text-sm)', padding: 'var(--space-2)' }}>{error}</Alert>}
      </div>
    </aside>
  );
}
