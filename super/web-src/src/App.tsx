import { useCallback, useEffect, useMemo, useState } from 'react';
import ChatView from './components/ChatView';
import TreeView from './components/TreeView';
import ApproveView from './components/ApproveView';
import ReportView from './components/ReportView';
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
  const {
    model, setModel, models, workspace, setWorkspace, reloadFlash, setReloadFlash,
    tasks, gates, criticals, error, setError, offlinePending, stats, refresh, fetchModels, fetchWorkspace,
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

  const paletteItems = useMemo(() => [
    { id: 'chat', label: 'Go to Chat', hint: '1 / ⌘K', action: () => setView('chat') },
    { id: 'tree', label: 'Go to Job Tree', hint: '2', action: () => setView('tree') },
    { id: 'approve', label: 'Go to Approve', hint: '3', action: () => setView('approve') },
    { id: 'report', label: 'Go to Report', hint: '4', action: () => setView('report') },
    { id: 'newchat', label: 'New chat', hint: 'c', action: () => window.dispatchEvent(new CustomEvent('super-new-chat')) },
    { id: 'refresh', label: 'Refresh data', action: () => void refresh() },
  ], [refresh, setView]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;
      if (e.key === '1') setView('chat');
      if (e.key === '2') setView('tree');
      if (e.key === '3') setView('approve');
      if (e.key === '4') setView('report');
      if (e.key === 'j' && view === 'tree') window.dispatchEvent(new CustomEvent('super-nav', { detail: 'next' }));
      if (e.key === 'k' && view === 'tree') window.dispatchEvent(new CustomEvent('super-nav', { detail: 'prev' }));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view, setView]);

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
      />

      <div className="app-main-wrap">
        <AppHeader
          view={view}
          stats={stats}
          model={model}
          models={models}
          reloadFlash={reloadFlash}
          setReloadFlash={setReloadFlash}
          onModelChange={setModel}
          setError={setError}
          refresh={refresh}
          fetchModels={fetchModels}
          fetchWorkspace={fetchWorkspace}
          onToggleMobile={() => setMobileNav((v) => !v)}
        />

        <main className="app-main" style={{ viewTransitionName: 'content' } as React.CSSProperties}>
          <div className="content-max">
            <ErrorBoundary>
              {route.view === 'chat' && (
                <ChatView sessionId={route.sessionId} onSessionIdChange={onSessionIdChange} />
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
            </ErrorBoundary>
          </div>
        </main>

        <AppFooter stats={stats} offlinePending={offlinePending} criticals={criticals} />
      </div>

      {mobileNav && <div className="drawer-scrim" onClick={() => setMobileNav(false)} aria-hidden />}
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
