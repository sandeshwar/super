import { api } from '../../api';
import { Icons } from '../ui/Icon';
import { ThemeToggle } from '../ThemeToggle';
import { modelShort } from '../../utils/format';
import { userMessage } from '../../lib/errors';
import type { View } from '../../lib/router';
import type { Stats } from './hooks/useAppData';

const VIEW_META: Record<View, { title: string; desc: string; icon: keyof typeof Icons }> = {
  chat: { title: 'Chat', desc: 'Grounded assistant · every reply verified against repo symbols', icon: 'chat' },
  tree: { title: 'Job Tree', desc: 'DAG of microtasks · leaf-only model, proven in order', icon: 'tree' },
  approve: { title: 'Approve', desc: 'Human-in-loop gate · fatigue-aware, critic-backed', icon: 'approve' },
  report: { title: 'Report Card', desc: 'Provenance ledger · gates, catch rates & criticals', icon: 'report' },
};

type Props = {
  view: View;
  stats: Stats;
  model: string;
  models: string[];
  reloadFlash: boolean;
  setReloadFlash: (v: boolean) => void;
  onModelChange: (m: string) => void;
  setError: (e: string | null) => void;
  refresh: () => void;
  fetchModels: () => void;
  fetchWorkspace: () => void;
  onToggleMobile: () => void;
};

export function AppHeader({ view, stats, model, models, reloadFlash, setReloadFlash, onModelChange, setError, refresh, fetchModels, fetchWorkspace, onToggleMobile }: Props) {
  const NavIcon = Icons[VIEW_META[view].icon];
  const modelLabel = model ? modelShort(model) : 'offline';
  const isOffline = !model;
  return (
    <header className="app-header">
      <button className="icon-btn menu-btn" aria-label="Open navigation" onClick={onToggleMobile}>
        <Icons.menu size={16} />
      </button>
      <div className="header-title" style={{ viewTransitionName: 'header' } as React.CSSProperties}>
        <h1><NavIcon size={14} style={{ color: 'var(--accent)' } as React.CSSProperties} />{VIEW_META[view].title} <small>{view === 'chat' ? 'grounded' : view === 'tree' ? `${stats.total} nodes` : view === 'approve' ? `${stats.pending} pending` : `${stats.proven}/${stats.total} proven`}</small></h1>
        <p>{VIEW_META[view].desc} <span className="mono muted" style={{ fontSize: 'var(--text-2xs)' }}>· 1/2/3/4 · j/k · / · ⌘K</span></p>
      </div>

      <div className="header-actions">
        <div className="search-wrap" style={{ display: view === 'tree' ? 'flex' : 'none' }} aria-hidden={view !== 'tree'}>
          <Icons.search size={14} />
          <input
            placeholder="Search tasks… (/)"
            aria-label="Search tasks"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const q = (e.currentTarget as HTMLInputElement).value;
                if (q) window.dispatchEvent(new CustomEvent('super-search', { detail: q }));
              }
            }}
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
                await api.setModel(m);
                onModelChange(m);
                setReloadFlash(true);
                setTimeout(() => setReloadFlash(false), 1500);
              } catch (err) { setError(userMessage(err)); }
            }}
            title={model || 'offline'}
            aria-label="Model selector"
            style={{ maxWidth: 190, padding: '5px 8px', borderRadius: 'var(--radius-full)', background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)' }}
          >
            {models.length ? models.map((m) => <option key={m} value={m}>{modelShort(m)}</option>) : <option value={model}>{modelLabel}</option>}
          </select>
          {reloadFlash && <span className="badge accent" style={{ position: 'absolute', top: -8, right: -8, fontSize: 9, padding: '1px 5px' }}>reloaded</span>}
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
          title="Hot reload harness (r)"
          aria-label="Hot reload"
          style={{ position: 'relative' }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 3v3H5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><path d="M5 8a5 5 0 108-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
          {reloadFlash && <span style={{ position: 'absolute', top: 2, right: 2, width: 6, height: 6, borderRadius: 99, background: 'var(--green)' }} />}
        </button>
        <ThemeToggle />
        <a className="icon-btn" href="/api/health" target="_blank" rel="noreferrer" title="Health JSON" aria-label="Health">
          <Icons.info size={14} />
        </a>
      </div>
    </header>
  );
}
