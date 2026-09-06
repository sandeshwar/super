/**
 * useAsync — reusable async state (S/R).
 * Single responsibility: loading/error/value lifecycle.
 */
import { useCallback, useEffect, useState } from 'react';
import { toAppError } from '../lib/errors';

export type AsyncState<T> = {
  value: T | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
};

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [value, setValue] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const v = await fn();
      setValue(v);
    } catch (e) {
      setError(toAppError(e));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { refresh(); }, [refresh]);

  return { value, loading, error, refresh };
}
