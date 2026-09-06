import { useCallback, useEffect, useRef, useState } from 'react';

type Queued = { id: string; fn: () => Promise<void>; tries: number };

/**
 * Offline queue — serializes POSTs when offline.
 * Single responsibility: queue + persistence (memory only, no IndexedDB to keep flat).
 */
export function useOfflineQueue() {
  const q = useRef<Queued[]>([]);
  const [pending, setPending] = useState(0);
  const processing = useRef(false);

  const drain = useCallback(async () => {
    if (processing.current) return;
    processing.current = true;
    while (q.current.length) {
      const item = q.current[0];
      try {
        await item.fn();
        q.current.shift();
        setPending(q.current.length);
      } catch {
        // drop failed item
        q.current.shift();
        setPending(q.current.length);
      }
    }
    processing.current = false;
  }, []);

  const enqueue = useCallback((fn: () => Promise<void>) => {
    const id = Math.random().toString(36).slice(2,8);
    q.current.push({ id, fn, tries: 0 });
    setPending(q.current.length);
    void drain();
    return id;
  }, [drain]);

  // auto-drain on online
  useEffect(() => {
    const on = () => void drain();
    window.addEventListener('online', on);
    return () => window.removeEventListener('online', on);
  }, [drain]);

  return { enqueue, pending, drain };
}
