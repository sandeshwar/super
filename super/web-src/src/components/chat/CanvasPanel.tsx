import { useEffect, useMemo, useRef, useState } from 'react';
import type { CanvasPart } from '../../types';
import { Markdown } from '../Markdown';
import { Button } from '../ui/Button';

export const CANVAS_CHANNEL = 'super-canvas';

export type CanvasChannelMsg =
  | { type: 'state'; artifacts: CanvasPart[]; activeId: string | null; open: boolean; detached: boolean }
  | { type: 'request_state' }
  | { type: 'reattach' }
  | { type: 'detached' };

export function mergeCanvas(
  prev: CanvasPart[] | undefined | null,
  next: CanvasPart | null | undefined,
): CanvasPart[] {
  if (!next || !next.id) return prev ? [...prev] : [];
  const list = prev ? [...prev] : [];
  const idx = list.findIndex((c) => c.id === next.id);
  if (next.action === 'close') {
    if (idx >= 0) list[idx] = { ...list[idx], ...next, open: false };
    else list.push({ ...next, open: false });
    return list;
  }
  if (idx >= 0) list[idx] = { ...list[idx], ...next };
  else list.push(next);
  return list;
}

export function collectOpenCanvases(
  messages: {
    canvas?: CanvasPart[];
    blocks?: { kind: string; canvas?: CanvasPart }[];
    tools?: { canvas?: CanvasPart }[];
  }[],
): CanvasPart[] {
  const byId = new Map<string, CanvasPart>();
  for (const m of messages) {
    for (const c of m.canvas || []) {
      if (c?.id) byId.set(c.id, c);
    }
    for (const b of m.blocks || []) {
      if (b.kind === 'canvas' && b.canvas?.id) byId.set(b.canvas.id, b.canvas);
    }
    for (const t of m.tools || []) {
      if (t.canvas?.id) byId.set(t.canvas.id, t.canvas);
    }
  }
  return [...byId.values()].filter((c) => c.action !== 'close' && c.open !== false);
}

/** @deprecated use collectOpenCanvases */
export function latestOpenCanvas(items: CanvasPart[] | undefined | null): CanvasPart | null {
  const open = (items || []).filter((c) => c && c.action !== 'close' && c.open !== false);
  return open.length ? open[open.length - 1] : null;
}

function isHttpSrc(src?: string): boolean {
  if (!src) return false;
  return /^(https?:)?\/\//i.test(src) || src.startsWith('/') || src.startsWith('data:');
}

function CanvasBody({ artifact }: { artifact: CanvasPart }) {
  const kind = (artifact.kind || 'markdown').toLowerCase();
  const src = artifact.src;

  if (kind === 'url' && src && isHttpSrc(src)) {
    if (artifact.embeddable === false) {
      return (
        <div className="canvas-embed-blocked">
          <p className="canvas-embed-title">{artifact.title || 'Page'}</p>
          <p className="small muted">
            {artifact.embed_note || 'This site blocks embedding in an iframe.'}
          </p>
          <div className="canvas-embed-actions">
            <Button size="sm" variant="primary" onClick={() => window.open(src, '_blank', 'noopener,noreferrer')}>
              Open in new tab
            </Button>
            <code className="mono small">{src}</code>
          </div>
        </div>
      );
    }
    return (
      <iframe
        className="canvas-frame"
        title={artifact.title || 'Canvas'}
        src={src}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
        referrerPolicy="no-referrer"
      />
    );
  }

  if (kind === 'image' && src) {
    return (
      <div className="canvas-media-wrap">
        <img className="canvas-image" src={src} alt={artifact.alt || artifact.title || 'image'} />
      </div>
    );
  }

  if (kind === 'video' && src) {
    return (
      <div className="canvas-media-wrap">
        <video className="canvas-video" src={src} controls playsInline />
      </div>
    );
  }

  if (kind === 'html') {
    if (src && isHttpSrc(src) && !src.startsWith('data:')) {
      return (
        <iframe
          className="canvas-frame"
          title={artifact.title || 'HTML'}
          src={src}
          sandbox="allow-scripts allow-same-origin"
          referrerPolicy="no-referrer"
        />
      );
    }
    return (
      <iframe
        className="canvas-frame"
        title={artifact.title || 'HTML'}
        srcDoc={artifact.content || ''}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
      />
    );
  }

  if (kind === 'markdown' || kind === 'doc') {
    if (artifact.content) {
      return (
        <div className="canvas-doc">
          <Markdown content={artifact.content} />
        </div>
      );
    }
    if (src && isHttpSrc(src)) {
      return (
        <iframe
          className="canvas-frame"
          title={artifact.title || 'Document'}
          src={src}
          sandbox="allow-same-origin"
          referrerPolicy="no-referrer"
        />
      );
    }
  }

  if (kind === 'file' || kind === 'doc') {
    const label = artifact.alt || artifact.path || src || 'file';
    return (
      <div className="canvas-file muted">
        <p className="small">File preview unavailable.</p>
        {src && isHttpSrc(src) ? (
          <a href={src} target="_blank" rel="noreferrer">{label}</a>
        ) : (
          <code className="mono">{label}</code>
        )}
      </div>
    );
  }

  return (
    <div className="canvas-empty muted small">
      Nothing to render for kind <code>{kind}</code>.
    </div>
  );
}

export function CanvasPanel({
  artifacts,
  activeId,
  open,
  detached,
  onSelect,
  onOpenChange,
  onClose,
  onCloseOne,
  onDetach,
  onReattach,
  popout = false,
}: {
  artifacts: CanvasPart[];
  activeId: string | null;
  open: boolean;
  detached?: boolean;
  onSelect?: (id: string) => void;
  onOpenChange?: (open: boolean) => void;
  onClose?: () => void;
  onCloseOne?: (id: string) => void;
  onDetach?: () => void;
  onReattach?: () => void;
  popout?: boolean;
}) {
  const active = artifacts.find((a) => a.id === activeId) || artifacts[artifacts.length - 1] || null;
  const hasArtifacts = artifacts.length > 0;

  // Collapsed rail when user collapsed but artifacts exist
  if (!popout && hasArtifacts && !open && !detached) {
    return (
      <aside className="canvas-rail" aria-label="Canvas collapsed">
        <button
          type="button"
          className="canvas-rail-btn"
          onClick={() => onOpenChange?.(true)}
          title="Expand canvas"
        >
          <span>Canvas</span>
          <span className="mono">{artifacts.length}</span>
        </button>
      </aside>
    );
  }

  if (!popout && detached) {
    return (
      <aside className="canvas-panel canvas-panel-detached canvas-panel-outer" aria-label="Canvas detached">
        <div className="canvas-panel-head">
          <span>Canvas</span>
          <span className="mono head-meta">detached</span>
        </div>
        <div className="canvas-detached-body muted small">
          Open in a separate window.
          {onReattach && (
            <Button size="sm" variant="ghost" onClick={onReattach}>
              Reattach
            </Button>
          )}
        </div>
      </aside>
    );
  }

  if (!popout && (!open || !hasArtifacts)) {
    return null;
  }

  const title = active?.title || 'Canvas';
  const kind = active?.kind || '';

  return (
    <aside className={`canvas-panel canvas-panel-outer${popout ? ' canvas-panel-popout' : ''}`} aria-label="Canvas">
      <div className="canvas-panel-head">
        <div className="canvas-panel-titles">
          <span className="canvas-panel-title" title={title}>{title}</span>
          {kind ? <span className="mono canvas-kind">{kind}</span> : null}
        </div>
        <div className="canvas-panel-actions">
          {!popout && active?.detachable !== false && onDetach && (
            <Button size="sm" variant="ghost" onClick={onDetach} title="Open in new window">
              Pop out
            </Button>
          )}
          {popout && onReattach && (
            <Button size="sm" variant="ghost" onClick={onReattach} title="Return to chat">
              Dock
            </Button>
          )}
          {!popout && onOpenChange && (
            <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)} title="Collapse">
              Collapse
            </Button>
          )}
          {onClose && (
            <Button size="sm" variant="ghost" onClick={onClose} title="Close all">
              Close
            </Button>
          )}
        </div>
      </div>

      {artifacts.length > 1 && (
        <div className="canvas-tabs" role="tablist" aria-label="Canvas artifacts">
          {artifacts.map((a) => {
            const selected = a.id === (active?.id || '');
            return (
              <button
                key={a.id}
                type="button"
                role="tab"
                aria-selected={selected}
                className={`canvas-tab${selected ? ' is-active' : ''}`}
                onClick={() => onSelect?.(a.id)}
                title={a.title || a.id}
              >
                <span className="canvas-tab-label">{a.title || a.kind || a.id}</span>
                <span className="mono canvas-tab-kind">{a.kind}</span>
                {onCloseOne && (
                  <span
                    className="canvas-tab-close"
                    role="button"
                    tabIndex={0}
                    aria-label={`Close ${a.title || a.id}`}
                    onClick={(e) => { e.stopPropagation(); onCloseOne(a.id); }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        e.stopPropagation();
                        onCloseOne(a.id);
                      }
                    }}
                  >
                    ×
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      <div className="canvas-panel-body">
        {active ? <CanvasBody artifact={active} /> : (
          <div className="canvas-empty muted small">No artifact.</div>
        )}
      </div>
    </aside>
  );
}

/** Standalone popout page — syncs via BroadcastChannel. */
export function CanvasPopoutView() {
  const [artifacts, setArtifacts] = useState<CanvasPart[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const bcRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => {
    const bc = new BroadcastChannel(CANVAS_CHANNEL);
    bcRef.current = bc;
    bc.onmessage = (ev: MessageEvent<CanvasChannelMsg>) => {
      const msg = ev.data;
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'state') {
        setArtifacts(msg.artifacts || []);
        setActiveId(msg.activeId);
        setOpen(msg.open);
      }
    };
    bc.postMessage({ type: 'request_state' } satisfies CanvasChannelMsg);
    bc.postMessage({ type: 'detached' } satisfies CanvasChannelMsg);
    return () => {
      bc.postMessage({ type: 'reattach' } satisfies CanvasChannelMsg);
      bc.close();
      bcRef.current = null;
    };
  }, []);

  const onReattach = () => {
    bcRef.current?.postMessage({ type: 'reattach' } satisfies CanvasChannelMsg);
    window.close();
  };

  return (
    <div className="canvas-popout-root">
      <CanvasPanel
        artifacts={artifacts}
        activeId={activeId}
        open={open}
        popout
        onSelect={setActiveId}
        onReattach={onReattach}
        onClose={onReattach}
      />
    </div>
  );
}

/** Hook: session-scoped multi-artifact canvas state. */
export function useCanvasController(
  messages: {
    canvas?: CanvasPart[];
    blocks?: { kind: string; canvas?: CanvasPart }[];
    tools?: { canvas?: CanvasPart }[];
  }[],
  sessionKey?: string | null,
) {
  const fromMessages = useMemo(() => collectOpenCanvases(messages), [messages]);
  const [live, setLive] = useState<CanvasPart[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const CANVAS_COLLAPSE_KEY = 'super-canvas-collapsed';

  const readCollapsed = () => {
    try { return localStorage.getItem(CANVAS_COLLAPSE_KEY) === '1'; } catch { return false; }
  };

  const [open, setOpenState] = useState(() => !readCollapsed());
  const [userCollapsed, setUserCollapsed] = useState(readCollapsed);
  const [detached, setDetached] = useState(false);
  const bcRef = useRef<BroadcastChannel | null>(null);
  const stateRef = useRef({
    artifacts: [] as CanvasPart[],
    activeId: null as string | null,
    open: false,
    detached: false,
  });

  const setOpen = (v: boolean) => {
    setOpenState(v);
    setUserCollapsed(!v);
    try { localStorage.setItem(CANVAS_COLLAPSE_KEY, v ? '0' : '1'); } catch { /* ignore */ }
  };

  useEffect(() => {
    setLive([]);
    setActiveId(null);
    setDetached(false);
    // Restore collapse preference when switching chats (don't force open/closed).
    const collapsed = readCollapsed();
    setUserCollapsed(collapsed);
    setOpenState(!collapsed);
  }, [sessionKey]);

  const artifacts = useMemo(() => {
    let list = [...fromMessages];
    for (const c of live) list = mergeCanvas(list, c);
    return list.filter((c) => c.action !== 'close' && c.open !== false);
  }, [fromMessages, live]);

  useEffect(() => {
    stateRef.current = { artifacts, activeId, open, detached };
  }, [artifacts, activeId, open, detached]);

  useEffect(() => {
    const bc = new BroadcastChannel(CANVAS_CHANNEL);
    bcRef.current = bc;
    bc.onmessage = (ev: MessageEvent<CanvasChannelMsg>) => {
      const msg = ev.data;
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'request_state') {
        const s = stateRef.current;
        bc.postMessage({
          type: 'state',
          artifacts: s.artifacts,
          activeId: s.activeId,
          open: s.open,
          detached: true,
        } satisfies CanvasChannelMsg);
      } else if (msg.type === 'detached') {
        setDetached(true);
      } else if (msg.type === 'reattach') {
        setDetached(false);
        setOpen(true);
      }
    };
    return () => {
      bc.close();
      bcRef.current = null;
    };
  }, []);

  const artifactKey = useMemo(() => artifacts.map((a) => a.id).join('|'), [artifacts]);

  // Focus newest artifact; only auto-expand if user hasn't collapsed the panel.
  useEffect(() => {
    if (!artifacts.length) {
      setActiveId(null);
      return;
    }
    const newest = artifacts[artifacts.length - 1];
    setActiveId((prev) => (prev && artifacts.some((a) => a.id === prev) ? prev : newest.id));
    if (!userCollapsed) setOpenState(true);
  }, [artifactKey, artifacts, userCollapsed]);

  useEffect(() => {
    if (!detached) return;
    bcRef.current?.postMessage({
      type: 'state',
      artifacts,
      activeId,
      open: true,
      detached: true,
    } satisfies CanvasChannelMsg);
  }, [artifacts, activeId, detached]);

  const detach = () => {
    setDetached(true);
    window.open('/canvas', 'super-canvas', 'width=960,height=720');
    window.setTimeout(() => {
      bcRef.current?.postMessage({
        type: 'state',
        artifacts: stateRef.current.artifacts,
        activeId: stateRef.current.activeId,
        open: true,
        detached: true,
      } satisfies CanvasChannelMsg);
    }, 300);
  };

  const reattach = () => {
    setDetached(false);
    setOpen(true);
    bcRef.current?.postMessage({ type: 'reattach' } satisfies CanvasChannelMsg);
  };

  const close = () => {
    setOpen(false);
    setLive(artifacts.map((a) => ({ ...a, action: 'close' as const, open: false })));
    setActiveId(null);
  };

  const closeOne = (id: string) => {
    setLive((prev) => {
      const base = prev.length ? prev : artifacts;
      return mergeCanvas(base, { id, action: 'close', open: false, kind: 'markdown' });
    });
  };

  return {
    artifacts,
    activeId,
    open: open && artifacts.length > 0,
    detached,
    setOpen,
    setActiveId,
    detach,
    reattach,
    close,
    closeOne,
    hasArtifacts: artifacts.length > 0,
  };
}
