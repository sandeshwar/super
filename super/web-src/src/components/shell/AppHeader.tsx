import { api } from '../../api';
import { Icons } from '../ui/Icon';
import { ThemeToggle } from '../ThemeToggle';
import { modelShort } from '../../utils/format';
import { userMessage } from '../../lib/errors';
import { VIEW_META } from '../../lib/labels';
import type { View } from '../../lib/router';
import type { Stats } from './hooks/useAppData';
import type { RefObject } from 'react';

type Props = {
  view: View;
  stats: Stats;
  model: string;
  models: string[];
  reloadFlash: boolean;
  setReloadFlash: (v: boolean) => void;
  onModelChange: (m: string, contextLength?: number | null) => void;
  setError: (e: string | null) => void;
  refresh: () => void;
  fetchModels: () => void;
  fetchWorkspace: () => void;
  onToggleMobile: () => void;
  mobileNav: boolean;
  menuBtnRef?: RefObject<HTMLButtonElement | null>;
  treeQ: string;
  onTreeQ: (q: string) => void;
};

export function AppHeader({
  view, stats, model, models, reloadFlash, setReloadFlash, onModelChange, setError,
  refresh, fetchModels, fetchWorkspace, onToggleMobile, mobileNav, menuBtnRef, treeQ, onTreeQ,
}: Props) {
  const NavIcon = Icons[VIEW_META[view].icon];
  const modelLabel = model ? modelShort(model) : 'offline';
  const isOffline = !model;
  const sub =
    view === 'chat' ? 'generalist · tools · specialists' :
    view === 'tree' ? `${stats.total} tasks` :
    view === 'approve' ? `${stats.pending} to review` :
    view === 'settings' ? 'model · look · tools' :
    `${stats.proven}/${stats.total} done`;

  return (
    <header className="app-header">
      <button
        ref={menuBtnRef}
        className="icon-btn menu-btn"
        aria-label={mobileNav ? 'Close menu' : 'Open menu'}
        aria-expanded={mobileNav}
        aria-controls="app-sidebar"
        onClick={onToggleMobile}
      >
        <Icons.menu size={16} />
      </button>
      <div className="header-title" style={{ viewTransitionName: 'header' } as React.CSSProperties}>
        <h1>
          <NavIcon size={14} style={{ color: 'var(--accent)' } as React.CSSProperties} />
          {VIEW_META[view].title}{' '}
          <small>{sub}</small>
        </h1>
        {view !== 'chat' && (
          <p>
            {VIEW_META[view].desc}{' '}
            <span className="mono muted" style={{ fontSize: 'var(--text-2xs)' }}>
              · 1–5 switch · {view === 'tree' ? 'j/k · / search · ' : ''}⌘K · r refresh · c new chat
            </span>
          </p>
        )}
      </div>

      <div className="header-actions">
        <div className="search-wrap" style={{ display: view === 'tree' ? 'flex' : 'none' }} aria-hidden={view !== 'tree'}>
          <Icons.search size={14} />
          <input
            id="header-task-search"
            value={treeQ}
            onChange={(e) => onTreeQ(e.target.value)}
            placeholder="Search tasks… (/)"
            aria-label="Search tasks"
          />
        </div>
        <div className="header-divider" aria-hidden />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, position: 'relative' }}>
          <span className="pulse" style={{ width: 7, height: 7, borderRadius: 99, background: isOffline ? 'var(--yellow)' : 'var(--green)', flexShrink: 0 }} aria-hidden />
          <select
            value={model}
            onChange={async (e) => {
              const m = e.target.value;
              try {
                const r = await api.setModel(m);
                onModelChange(m, r.context_length ?? null);
                setReloadFlash(true);
                setTimeout(() => setReloadFlash(false), 1500);
              } catch (err) { setError(userMessage(err)); }
            }}
            title={model || 'offline'}
            aria-label="Model"
            style={{ maxWidth: 190, padding: '5px 8px', borderRadius: 'var(--radius-full)', background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)' }}
          >
            {models.length ? models.map((m) => <option key={m} value={m}>{modelShort(m)}</option>) : <option value={model}>{modelLabel}</option>}
          </select>
          {reloadFlash && <span className="badge accent" style={{ position: 'absolute', top: -8, right: -8, fontSize: 9, padding: '1px 5px' }}>updated</span>}
        </div>
        <button
          className="icon-btn"
          onClick={async () => {
            try {
              await api.reload();
              setReloadFlash(true);
              setTimeout(() => setReloadFlash(false), 1500);
              void refresh();
              void fetchModels();
              void fetchWorkspace();
            } catch (err) { setError(userMessage(err)); }
          }}
          title="Reload (r)"
          aria-label="Reload"
          style={{ position: 'relative' }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3v3H5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><path d="M5 8a5 5 0 108-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          {reloadFlash && <span style={{ position: 'absolute', top: 2, right: 2, width: 6, height: 6, borderRadius: 99, background: 'var(--green)' }} />}
        </button>
        <ThemeToggle />
        <a className="icon-btn" href="/api/health" target="_blank" rel="noreferrer" title="Health" aria-label="Health">
          <Icons.info size={14} />
        </a>
      </div>
    </header>
  );
}
