import { useCallback, useSyncExternalStore } from 'react';

export type Theme = 'dark' | 'light';
export type Density = 'comfortable' | 'compact';

const THEME_KEY = 'super_theme';
const DENSITY_KEY = 'super_density';
const MOTION_KEY = 'super_reduce_motion';

type AppearanceState = {
  theme: Theme;
  density: Density;
  reduceMotion: boolean;
};

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY) as Theme | null;
    if (saved === 'light' || saved === 'dark') return saved;
    if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  } catch { /* ignore */ }
  return 'dark';
}

function readDensity(): Density {
  try {
    const saved = localStorage.getItem(DENSITY_KEY) as Density | null;
    if (saved === 'comfortable' || saved === 'compact') return saved;
  } catch { /* ignore */ }
  return 'comfortable';
}

function readReduceMotion(): boolean {
  try {
    const saved = localStorage.getItem(MOTION_KEY);
    if (saved === '1') return true;
    if (saved === '0') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch { /* ignore */ }
  return false;
}

let state: AppearanceState = {
  theme: typeof window !== 'undefined' ? readTheme() : 'dark',
  density: typeof window !== 'undefined' ? readDensity() : 'comfortable',
  reduceMotion: typeof window !== 'undefined' ? readReduceMotion() : false,
};

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function applyDom(s: AppearanceState) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', s.theme);
  document.documentElement.setAttribute('data-density', s.density);
  document.documentElement.setAttribute('data-reduce-motion', s.reduceMotion ? '1' : '0');
}

applyDom(state);

function persist(s: AppearanceState) {
  try {
    localStorage.setItem(THEME_KEY, s.theme);
    localStorage.setItem(DENSITY_KEY, s.density);
    localStorage.setItem(MOTION_KEY, s.reduceMotion ? '1' : '0');
  } catch { /* ignore */ }
}

function setState(patch: Partial<AppearanceState>) {
  state = { ...state, ...patch };
  persist(state);
  applyDom(state);
  emit();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

function getSnapshot() {
  return state;
}

export function useTheme() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const setTheme = useCallback((theme: Theme) => setState({ theme }), []);
  const toggle = useCallback(() => setState({ theme: state.theme === 'dark' ? 'light' : 'dark' }), []);
  return { theme: s.theme, setTheme, toggle };
}

export function useAppearance() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    ...s,
    setTheme: (theme: Theme) => setState({ theme }),
    setDensity: (density: Density) => setState({ density }),
    setReduceMotion: (reduceMotion: boolean) => setState({ reduceMotion }),
    toggleTheme: () => setState({ theme: state.theme === 'dark' ? 'light' : 'dark' }),
  };
}
