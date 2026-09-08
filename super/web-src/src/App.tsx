import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ChatView from './components/ChatView';
import SettingsView from './components/SettingsView';
import { CanvasPopoutView } from './components/chat/CanvasPanel';
import { ErrorBoundary } from './components/ErrorBoundary';
import { CommandPalette } from './components/CommandPalette';
import { Sidebar } from './components/shell/Sidebar';
import { AppHeader } from './components/shell/AppHeader';
import { AppFooter } from './components/shell/AppFooter';
import { useAppData } from './components/shell/hooks/useAppData';
import { RouterProvider, useRouter, type View } from './lib/router';
import './App.css';

function CanvasShell() {
  return (
    <ErrorBoundary>
      <CanvasPopoutView />
    </ErrorBoundary>
  );
}

function MainShell() {
  const { route, view, navigate } = useRouter();
  const [mobileNav, setMobileNav] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('super-sidebar-collapsed') === '1'; } catch { return false; }
  });
  const menuBtnRef = useRef<HTMLButtonElement | null>(null);
  const {
    model, setModel, models, contextLength, setContextLength,
    think, setThink, thinkLevels, applyThinkMeta,
    workspace, setWorkspace, reloadFlash, setReloadFlash,
    gates, criticals, error, setError, offlinePending, loading, stats,
    refresh, fetchModels, fetchWorkspace,
  } = useAppData();

  const setView = useCallback((v: View) => {
    if (v === 'chat') navigate({ view: 'chat', sessionId: route.view === 'chat' ? route.sessionId : null });
    else if (v === 'settings') navigate({ view: 'settings' });
    else if (v === 'canvas') navigate({ view: 'canvas' });
  }, [navigate, route]);

  const onSessionIdChange = useCallback((id: string | null) => {
    navigate({ view: 'chat', sessionId: id }, { replace: !id });
  }, [navigate]);

  const paletteItems = useMemo(() => [
    { id: 'chat', label: 'Go to Chat', hint: '1', action: () => setView('chat') },
    { id: 'settings', label: 'Go to Settings', hint: '2', action: () => setView('settings') },
    { id: 'newchat', label: 'New chat', hint: 'c', action: () => window.dispatchEvent(new CustomEvent('super-new-chat')) },
    { id: 'refresh', label: 'Refresh data', hint: 'r', action: () => void refresh() },
  ], [refresh, setView]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return;
      if (e.key === '1') setView('chat');
      if (e.key === '2') setView('settings');
      if (e.key === 'c') window.dispatchEvent(new CustomEvent('super-new-chat'));
      if (e.key === 'r') void refresh();
      if (e.key === 'Escape' && mobileNav) setMobileNav(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view, setView, refresh, mobileNav]);

  useEffect(() => {
    let startX = 0;
    const onTouchStart = (e: TouchEvent) => { startX = e.touches[0].clientX; };
    const onTouchMove = (e: TouchEvent) => {
      if (startX < 24 && e.touches[0].clientX - startX > 60) setMobileNav(true);
      if (startX > 200 && e.touches[0].clientX - startX < -60) setMobileNav(false);
    };
    window.addEventListener('touchstart', onTouchStart);
    window.addEventListener('touchmove', onTouchMove);
    return () => { window.removeEventListener('touchstart', onTouchStart); window.removeEventListener('touchmove', onTouchMove); };
  }, []);

  useEffect(() => { setMobileNav(false); }, [view, route]);

  useEffect(() => {
    const main = document.querySelector('.app-main-wrap');
    if (main) {
      if (mobileNav) main.setAttribute('inert', '');
      else main.removeAttribute('inert');
    }
  }, [mobileNav]);

  const toggleSidebarCollapsed = useCallback(() => {
    setSidebarCollapsed((v) => {
      const next = !v;
      try { localStorage.setItem('super-sidebar-collapsed', next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  }, []);

  return (
    <div className={`app-shell${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <CommandPalette items={paletteItems} />
      <Sidebar
        view={view}
        gates={gates}
        criticals={criticals}
        stats={stats}
        workspace={workspace}
        onWorkspaceChange={setWorkspace}
        reloadFlash={reloadFlash}
        setReloadFlash={setReloadFlash}
        error={error}
        setError={setError}
        offlinePending={offlinePending}
        mobileNav={mobileNav}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => {
          if (window.matchMedia('(max-width: 820px)').matches) setMobileNav((v) => !v);
          else toggleSidebarCollapsed();
        }}
        refresh={refresh}
      />

      <div className="app-main-wrap">
        <AppHeader
          view={view}
          stats={stats}
          model={model}
          models={models}
          think={think}
          thinkLevels={thinkLevels}
          reloadFlash={reloadFlash}
          setReloadFlash={setReloadFlash}
          onModelChange={(m, ctx) => {
            setModel(m);
            if (ctx !== undefined) setContextLength(typeof ctx === 'number' && ctx > 0 ? ctx : null);
          }}
          onThinkChange={(level, meta) => {
            if (meta?.think_levels) {
              applyThinkMeta({ think: level, think_levels: meta.think_levels });
            } else {
              setThink(level);
            }
          }}
          setError={setError}
          refresh={refresh}
          fetchModels={fetchModels}
          fetchWorkspace={fetchWorkspace}
          mobileNav={mobileNav}
          menuBtnRef={menuBtnRef}
          onToggleMobile={() => setMobileNav((v) => !v)}
        />

        <main className="app-main" style={{ viewTransitionName: 'content' } as React.CSSProperties}>
          <div className="content-max">
            {loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', padding: 'var(--space-4) 0' }} aria-busy="true" aria-label="Loading">
                <div className="skeleton" style={{ height: 48 }} />
                <div className="skeleton" style={{ height: 160 }} />
                <div className="skeleton" style={{ height: 240 }} />
              </div>
            ) : (
              <ErrorBoundary>
                {route.view === 'chat' && (
                  <ChatView
                    sessionId={route.sessionId}
                    onSessionIdChange={onSessionIdChange}
                    contextLength={contextLength}
                  />
                )}
                {route.view === 'settings' && (
                  <SettingsView
                    model={model}
                    models={models}
                    think={think}
                    thinkLevels={thinkLevels}
                    workspace={workspace}
                    onModelChange={(m) => setModel(m)}
                    onThinkChange={(level, meta) => {
                      if (meta?.think_levels) applyThinkMeta({ think: level, think_levels: meta.think_levels });
                      else setThink(level);
                    }}
                    onWorkspaceChange={setWorkspace}
                    fetchModels={fetchModels}
                    fetchWorkspace={fetchWorkspace}
                    refresh={refresh}
                    onContextLength={(n) => setContextLength(typeof n === 'number' && n > 0 ? n : null)}
                  />
                )}
              </ErrorBoundary>
            )}
          </div>
        </main>

        <AppFooter
          stats={stats}
          offlinePending={offlinePending}
          criticals={criticals}
          onDrainOffline={() => window.dispatchEvent(new Event('online'))}
        />
      </div>

      {mobileNav && (
        <div
          className="drawer-scrim"
          onClick={() => setMobileNav(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setMobileNav(false); }}
          role="presentation"
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <RouterProvider>
      <AppShell />
    </RouterProvider>
  );
}

function AppShell() {
  const { route } = useRouter();
  if (route.view === 'canvas') return <CanvasShell />;
  return <MainShell />;
}
