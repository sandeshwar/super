import { useCallback, useEffect, useState } from 'react';

type Queued = {
  id: string;
  fn: () => Promise<void>;
  tries: number;
  label?: string;
};

type Listener = (pending: number) => void;

const MAX_TRIES = 5;
const BASE_DELAY_MS = 800;

/**
 * Single shared offline queue (all views). Retries with backoff; never silent-drops
 * until MAX_TRIES. Subscribe via useOfflineQueue().
 */
class OfflineQueue {
  private q: Queued[] = [];
  private processing = false;
  private listeners = new Set<Listener>();

  get pending() { return this.q.length; }

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    fn(this.q.length);
    return () => { this.listeners.delete(fn); };
  }

  private emit() {
    const n = this.q.length;
    this.listeners.forEach((l) => l(n));
  }

  enqueue = (fn: () => Promise<void>, label?: string) => {
    const id = Math.random().toString(36).slice(2, 8);
    this.q.push({ id, fn, tries: 0, label });
    this.emit();
    void this.drain();
    return id;
  };

  drain = async () => {
    if (this.processing) return;
    this.processing = true;
    while (this.q.length) {
      if (typeof navigator !== 'undefined' && !navigator.onLine) break;
      const item = this.q[0];
      try {
        await item.fn();
        this.q.shift();
        this.emit();
      } catch {
        item.tries += 1;
        if (item.tries >= MAX_TRIES) {
          this.q.shift();
          this.emit();
          continue;
        }
        this.emit();
        await new Promise((r) => setTimeout(r, BASE_DELAY_MS * 2 ** (item.tries - 1)));
      }
    }
    this.processing = false;
  };
}

export const offlineQueue = new OfflineQueue();

export function useOfflineQueue() {
  const [pending, setPending] = useState(offlineQueue.pending);
  useEffect(() => offlineQueue.subscribe(setPending), []);

  useEffect(() => {
    const on = () => void offlineQueue.drain();
    window.addEventListener('online', on);
    return () => window.removeEventListener('online', on);
  }, []);

  const enqueue = useCallback((fn: () => Promise<void>, label?: string) => offlineQueue.enqueue(fn, label), []);
  const drain = useCallback(() => offlineQueue.drain(), []);

  return { enqueue, pending, drain };
}
