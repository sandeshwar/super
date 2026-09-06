import { useMemo } from 'react';

/**
 * Simple windowed virtualization (no dep) — assumes fixed row height.
 * Returns slice [start,end) for container height / scrollTop.
 */
export function useVirtual(count: number, rowH: number, containerH: number, scrollTop: number, overscan = 5) {
  return useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / rowH) - overscan);
    const visible = Math.ceil(containerH / rowH) + overscan * 2;
    const end = Math.min(count, start + visible);
    const offset = start * rowH;
    const total = count * rowH;
    return { start, end, offset, total };
  }, [count, rowH, containerH, scrollTop, overscan]);
}
