import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../../api';
import type { TaskNode } from '../../../types';
import { useOfflineQueue } from '../../../hooks/useOfflineQueue';
import { userMessage } from '../../../lib/errors';

export type Stats = { proven: number; total: number; pct: number; gatePass: number; gateReject: number; pending: number; waiting: number; doing: number };

export function useAppData() {
  const [model, setModel] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [workspace, setWorkspace] = useState('');
  const [reloadFlash, setReloadFlash] = useState(false);
  const [tasks, setTasks] = useState<TaskNode[]>([]);
  const [gates, setGates] = useState<Record<string, { pass: number; reject: number }>>({});
  const [criticals, setCriticals] = useState<unknown[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { pending: offlinePending, enqueue } = useOfflineQueue();

  useEffect(() => { (window as unknown as { superEnqueue: typeof enqueue }).superEnqueue = enqueue; }, [enqueue]);

  const refresh = useCallback(async () => {
    try {
      const [h, t, l] = await Promise.all([api.health(), api.tree(), api.ledger()]);
      setModel(h.model ?? '');
      setTasks(t.tasks);
      setGates(l.gates);
      setCriticals(l.open_criticals);
      setError(null);
    } catch (e) {
      const msg = userMessage(e);
      if (!String(msg).toLowerCase().includes('unauthorized')) setError(msg);
    }
  }, []);

  const fetchModels = useCallback(async () => {
    try {
      const r = await api.models();
      setModels(r.models);
      if (r.current) setModel(r.current);
    } catch {}
  }, []);

  const fetchWorkspace = useCallback(async () => {
    try {
      const w = await api.workspace();
      setWorkspace(w.workspace);
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
    fetchModels();
    fetchWorkspace();
    const id = window.setInterval(refresh, 5000);
    const hotId = window.setInterval(async () => {
      try {
        const w = await api.workspace();
        if (w.workspace !== workspace && workspace) {
          setReloadFlash(true);
          setTimeout(() => setReloadFlash(false), 2000);
          setWorkspace(w.workspace);
          void refresh();
        }
        const m = await api.models();
        if (m.current !== model && model) {
          setReloadFlash(true);
          setTimeout(() => setReloadFlash(false), 2000);
          setModel(m.current);
        }
      } catch {}
    }, 3000);
    return () => { window.clearInterval(id); window.clearInterval(hotId); };
  }, [refresh, fetchModels, fetchWorkspace, workspace, model]);

  useEffect(() => {
    const onRefresh = () => void refresh();
    window.addEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
    return () => window.removeEventListener('super-refresh' as unknown as string, onRefresh as EventListener);
  }, [refresh]);

  const stats: Stats = useMemo(() => {
    const proven = tasks.filter((t) => t.status === 'proven').length;
    const total = tasks.length;
    const pct = total ? Math.round((proven / total) * 100) : 0;
    const gatePass = Object.values(gates).reduce((s, g) => s + g.pass, 0);
    const gateReject = Object.values(gates).reduce((s, g) => s + g.reject, 0);
    const waiting = tasks.filter((t) => t.status === 'waiting').length;
    const doing = tasks.filter((t) => t.status === 'doing').length;
    const pending = waiting + doing;
    return { proven, total, pct, gatePass, gateReject, pending, waiting, doing };
  }, [tasks, gates]);

  return {
    model, setModel, models, workspace, setWorkspace, reloadFlash, setReloadFlash,
    tasks, gates, criticals, error, setError, offlinePending,
    stats, refresh, fetchModels, fetchWorkspace,
  };
}
