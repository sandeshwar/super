import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ChatView from './components/ChatView';
import TreeView from './components/TreeView';
import ApproveView from './components/ApproveView';
import ReportView from './components/ReportView';
import SettingsView from './components/SettingsView';
import { ErrorBoundary } from './components/ErrorBoundary';
import { CommandPalette } from './components/CommandPalette';
import { Sidebar } from './components/shell/Sidebar';
import { AppHeader } from './components/shell/AppHeader';
import { AppFooter } from './components/shell/AppFooter';
import { useAppData } from './components/shell/hooks/useAppData';
import { RouterProvider, useRouter, type TreeFilter, type TreeSort, type View } from './lib/router';
import './App.css';

function AppShell() {
  const { route, view, navigate } = useRouter();
  const [mobileNav, setMobileNav] = useState(false);
  const menuBtnRef = useRef<HTMLButtonElement | null>(null);
  const {
    model, setModel, models, contextLength, setContextLength, workspace, setWorkspace, reloadFlash, setReloadFlash,
    tasks, gates, criticals, error, setError, offlinePending, loading, stats,
    refresh, fetchModels, fetchWorkspace,
  } = useAppData();

  const setView = useCallback((v: View) => {
    if (v === 'chat') navigate({ view: 'chat', sessionId: route.view === 'chat' ? route.sessionId : null });
    else if (v === 'tree') navigate({
      view: 'tree',
      taskId: route.view === 'tree' ? route.taskId : null,
      q: route.view === 'tree' ? route.q : '',
      status: route.view === 'tree' ? route.status : 'all',
      sort: route.view === 'tree' ? route.sort : 'id',
    });
    else if (v === 'approve') navigate({ view: 'approve', taskId: route.view === 'approve' ? route.taskId : null });
    else if (v === 'settings') navigate({ view: 'settings' });
    else navigate({ view: 'report' });
  }, [navigate, route]);

  const onSessionIdChange = useCallback((id: string | null) => {
    navigate({ view: 'chat', sessionId: id }, { replace: !id });
  }, [navigate]);

  const onTreeRouteChange = useCallback((patch: {
    taskId?: string | null; q?: string; status?: TreeFilter; sort?: TreeSort;
  }) => {
    if (route.view !== 'tree') return;
    navigate({
      view: 'tree',
      taskId: patch.taskId !== undefined ? patch.taskId : route.taskId,
      q: patch.q !== undefined ? patch.q : route.q,
      status: patch.status !== undefined ? patch.status : route.status,
      sort: patch.sort !== undefined ? patch.sort : route.sort,
    }, { replace: true });
  }, [navigate, route]);

  const onApproveTaskIdChange = useCallback((id: string | null) => {
    navigate({ view: 'approve', taskId: id }, { replace: true });
  }, [navigate]);

  const goResultsProblems = useCallback(() => {
    navigate({ view: 'report' });
    window.setTimeout(() => window.dispatchEvent(new CustomEvent('super-expand-criticals')), 50);
  }, [navigate]);

  const paletteItems = useMemo(() => [
    { id: 'chat', label: 'Go to Chat', hint: '1', action: () => setView('chat') },
    { id: 'tree', label: 'Go to Tasks', hint: '2', action: () => setView('tree') },
    { id: 'approve', label: 'Go to Review', hint: '3', action: () => setView('approve') },
    { id: 'report', label: 'Go to Results', hint: '4', action: () => setView('report') },
    { id: 'settings', label: 'Go to Settings', hint: '5', action: () => setView('settings') },
    { id: 'newchat', label: 'New chat', hint: 'c', action: () => window.dispatchEvent(new CustomEvent('super-new-chat')) },
    { id: 'refresh', label: 'Refresh data', hint: 'r', action: () => void refresh() },
    ...(criticals.length ? [{ id: 'problems', label: 'Open problems', hint: `${criticals.length}`, action: goResultsProblems }] : []),
  ], [refresh, setView, criticals.length, goResultsProblems]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return;
      if (e.key === '1') setView('chat');
      if (e.key === '2') setView('tree');
      if (e.key === '3') setView('approve');
      if (e.key === '4') setView('report');
      if (e.key === '5') setView('settings');
      if (e.key === 'j' && view === 'tree') window.dispatchEvent(new CustomEvent('super-nav', { detail: 'next' }));
      if (e.key === 'k' && view === 'tree') window.dispatchEvent(new CustomEvent('super-nav', { detail: 'prev' }));
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

  // Inert background while drawer open
  useEffect(() => {
    const main = document.querySelector('.app-main-wrap');
    if (main) {
      if (mobileNav) main.setAttribute('inert', '');
      else main.removeAttribute('inert');
    }
  }, [mobileNav]);

  return (
    <div className="app-shell">
      <CommandPalette items={paletteItems} />
      <Sidebar
        view={view}
        tasks={tasks}
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
        refresh={refresh}
        onOpenProblems={goResultsProblems}
      />

      <div className="app-main-wrap">
        <AppHeader
          view={view}
          stats={stats}
          model={model}
          models={models}
          reloadFlash={reloadFlash}
          setReloadFlash={setReloadFlash}
          onModelChange={(m, ctx) => {
            setModel(m);
            if (ctx !== undefined) setContextLength(typeof ctx === 'number' && ctx > 0 ? ctx : null);
          }}
          setError={setError}
          refresh={refresh}
          fetchModels={fetchModels}
          fetchWorkspace={fetchWorkspace}
          mobileNav={mobileNav}
          menuBtnRef={menuBtnRef}
          onToggleMobile={() => setMobileNav((v) => !v)}
          treeQ={route.view === 'tree' ? route.q : ''}
          onTreeQ={(q) => {
            if (route.view === 'tree') onTreeRouteChange({ q });
            else navigate({ view: 'tree', taskId: null, q, status: 'all', sort: 'id' });
          }}
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
                {route.view === 'tree' && (
                  <TreeView
                    tasks={tasks}
                    gates={gates}
                    taskId={route.taskId}
                    q={route.q}
                    status={route.status}
                    sort={route.sort}
                    onRouteChange={onTreeRouteChange}
                  />
                )}
                {route.view === 'approve' && (
                  <ApproveView
                    tasks={tasks}
                    gates={gates}
                    onRefresh={() => void refresh()}
                    taskId={route.taskId}
                    onTaskIdChange={onApproveTaskIdChange}
                  />
                )}
                {route.view === 'report' && <ReportView tasks={tasks} gates={gates} criticals={criticals} />}
                {route.view === 'settings' && (
                  <SettingsView
                    model={model}
                    models={models}
                    workspace={workspace}
                    onModelChange={(m) => setModel(m)}
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
          onOpenProblems={goResultsProblems}
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
