import { useEffect, useMemo, useState } from 'react';
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
import './App.css';

type View = 'chat' | 'tree' | 'approve' | 'report';

export default function App() {
  const [view, setView] = useState<View>('chat');
  const [mobileNav, setMobileNav] = useState(false);
  const {
    model, setModel, models, workspace, setWorkspace, reloadFlash, setReloadFlash,
    tasks, gates, criticals, error, setError, offlinePending, stats, refresh, fetchModels, fetchWorkspace,
  } = useAppData();

  const paletteItems = useMemo(() => [
    { id: 'chat', label: 'Go to Chat', hint: '1 / ⌘K', action: () => setView('chat') },
    { id: 'tree', label: 'Go to Job Tree', hint: '2', action: () => setView('tree') },
    { id: 'approve', label: 'Go to Approve', hint: '3', action: () => setView('approve') },
    { id: 'report', label: 'Go to Report', hint: '4', action: () => setView('report') },
    { id: 'newchat', label: 'New chat', hint: 'c', action: () => window.dispatchEvent(new CustomEvent('super-new-chat')) },
    { id: 'refresh', label: 'Refresh data', action: () => void refresh() },
  ], [refresh]);

  // Keyboard nav: numbers + j/k for tree
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
  }, [view]);

  // Mobile swipe
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

  return (
    <div className="app-shell">
      <CommandPalette items={paletteItems} />
      <Sidebar
        view={view}
        onViewChange={setView}
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
              {view === 'chat' && <ChatView />}
              {view === 'tree' && <TreeView tasks={tasks} gates={gates} />}
              {view === 'approve' && <ApproveView tasks={tasks} gates={gates} onRefresh={() => void refresh()} />}
              {view === 'report' && <ReportView tasks={tasks} gates={gates} criticals={criticals} />}
            </ErrorBoundary>
          </div>
        </main>

        <AppFooter stats={stats} offlinePending={offlinePending} criticals={criticals} />
      </div>

      {mobileNav && <div className="drawer-scrim" onClick={() => setMobileNav(false)} aria-hidden />}
    </div>
  );
}
