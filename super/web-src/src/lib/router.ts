/**
 * Lightweight History API router — no react-router dep.
 * Paths: /chat[/:id] | /settings | /canvas
 * Preserves unrelated search params (e.g. ?token=).
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from 'react';

export type View = 'chat' | 'settings' | 'canvas';

export type Route =
  | { view: 'chat'; sessionId: string | null }
  | { view: 'settings' }
  | { view: 'canvas' };

const VIEWS = new Set<View>(['chat', 'settings', 'canvas']);

const LISTENERS = new Set<() => void>();
let snapshot = locationSnapshot();

function locationSnapshot() {
  return `${window.location.pathname}${window.location.search}`;
}

function emit() {
  snapshot = locationSnapshot();
  LISTENERS.forEach((l) => l());
}

function subscribe(cb: () => void) {
  LISTENERS.add(cb);
  return () => { LISTENERS.delete(cb); };
}

function getSnapshot() {
  return snapshot;
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', emit);
}

function cleanSeg(s: string | null | undefined): string | null {
  if (!s) return null;
  const t = decodeURIComponent(s).trim();
  return t || null;
}

export function parsePath(pathname: string, _search = ''): Route {
  const segs = pathname.replace(/\/+$/, '').split('/').filter(Boolean);
  const viewRaw = segs[0] || 'chat';
  // Legacy SPA paths → chat
  if (viewRaw === 'tree' || viewRaw === 'approve' || viewRaw === 'report') {
    return { view: 'chat', sessionId: null };
  }
  const view: View = VIEWS.has(viewRaw as View) ? (viewRaw as View) : 'chat';
  const id = cleanSeg(segs[1] ?? null);
  if (view === 'settings') return { view: 'settings' };
  if (view === 'canvas') return { view: 'canvas' };
  return { view: 'chat', sessionId: id };
}

/** Build path+query for a route, merging preserved search params (token, etc.). */
export function hrefFor(route: Partial<Route> & { view: View }, currentSearch?: string): string {
  const qs = new URLSearchParams(currentSearch ?? (typeof window !== 'undefined' ? window.location.search : ''));
  let path = `/${route.view}`;
  if (route.view === 'chat' && route.sessionId) path += `/${encodeURIComponent(route.sessionId)}`;
  const q = qs.toString();
  return q ? `${path}?${q}` : path;
}

export type NavigateOpts = { replace?: boolean };

export function navigate(to: string | (Partial<Route> & { view: View }), opts: NavigateOpts = {}) {
  const url = typeof to === 'string' ? to : hrefFor(to);
  const abs = new URL(url, window.location.origin);
  const next = `${abs.pathname}${abs.search}`;
  const cur = `${window.location.pathname}${window.location.search}`;
  if (next === cur) {
    emit();
    return;
  }
  if (opts.replace) window.history.replaceState(null, '', next);
  else window.history.pushState(null, '', next);
  emit();
}

/** Normalize `/` → `/chat` once on boot (keeps token). */
export function normalizeInitialUrl() {
  const { pathname, search, hash } = window.location;
  if (pathname === '/' || pathname === '') {
    window.history.replaceState(null, '', `/chat${search}${hash}`);
    emit();
  }
}

type RouterValue = {
  path: string;
  route: Route;
  view: View;
  navigate: typeof navigate;
  hrefFor: (r: Partial<Route> & { view: View }) => string;
};

const RouterCtx = createContext<RouterValue | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const path = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const route = useMemo(() => {
    const qIdx = path.indexOf('?');
    const pathnameOnly = qIdx >= 0 ? path.slice(0, qIdx) : path;
    const searchOnly = qIdx >= 0 ? path.slice(qIdx) : '';
    return parsePath(pathnameOnly || '/', searchOnly);
  }, [path]);

  useEffect(() => { normalizeInitialUrl(); }, []);

  const href = useCallback((r: Partial<Route> & { view: View }) => hrefFor(r), []);

  const value = useMemo<RouterValue>(() => ({
    path,
    route,
    view: route.view,
    navigate,
    hrefFor: href,
  }), [path, route, href]);

  return createElement(RouterCtx.Provider, { value }, children);
}

export function useRouter(): RouterValue {
  const ctx = useContext(RouterCtx);
  if (!ctx) throw new Error('useRouter requires RouterProvider');
  return ctx;
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  to: Partial<Route> & { view: View };
  replace?: boolean;
};

export function Link({ to, replace, onClick, children, ...rest }: LinkProps) {
  const { hrefFor: href, navigate: go } = useRouter();
  const url = href(to);
  return createElement(
    'a',
    {
      ...rest,
      href: url,
      onClick: (e: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(e);
        if (e.defaultPrevented) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        const doc = document as unknown as { startViewTransition?: (cb: () => void) => void };
        const run = () => go(to, { replace });
        if (doc.startViewTransition) doc.startViewTransition(run);
        else run();
      },
    },
    children,
  );
}
