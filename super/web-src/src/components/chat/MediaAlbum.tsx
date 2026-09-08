import { useCallback, useEffect, useId, useState } from 'react';
import type { MediaPart } from '../../types';

function isImage(p: MediaPart): boolean {
  const kind = (p.kind || 'image').toLowerCase();
  if (kind === 'image') return true;
  const mime = (p.mime || '').toLowerCase();
  return mime.startsWith('image/');
}

function safeSrc(src: string): string | null {
  const s = (src || '').trim();
  if (!s) return null;
  if (s.startsWith('/api/media/')) return s;
  if (s.startsWith('data:image/')) return s;
  if (s.startsWith('https://') || s.startsWith('http://')) return s;
  return null;
}

export function MediaAlbum({
  items,
  compact,
  label,
}: {
  items: MediaPart[];
  /** Smaller thumbs (tool rail). */
  compact?: boolean;
  label?: string;
}) {
  const images = (items || []).filter((p) => p && isImage(p) && safeSrc(p.src));
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const titleId = useId();

  const close = useCallback(() => setOpenIdx(null), []);
  const open = openIdx != null ? images[openIdx] : null;

  useEffect(() => {
    if (openIdx == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowRight') setOpenIdx((i) => (i == null ? i : (i + 1) % images.length));
      if (e.key === 'ArrowLeft') setOpenIdx((i) => (i == null ? i : (i - 1 + images.length) % images.length));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openIdx, images.length, close]);

  if (!images.length) return null;

  return (
    <div className={`media-album${compact ? ' is-compact' : ''}`}>
      {label && <div className="media-album-label mono">{label}</div>}
      <div className="media-album-grid" role="list">
        {images.map((p, i) => {
          const src = safeSrc(p.src)!;
          return (
            <button
              key={`${p.id || src}-${i}`}
              type="button"
              className="media-album-thumb"
              role="listitem"
              onClick={() => setOpenIdx(i)}
              title={p.alt || p.path || 'Open image'}
            >
                      <img src={src} alt={p.alt || ''} loading="lazy" />
                      {(p.bytes != null || p.alt) && (
                        <span className="media-album-cap mono">
                          {p.alt || 'image'}
                          {p.bytes != null ? ` · ${(p.bytes / 1024).toFixed(p.bytes >= 102400 ? 0 : 1)} KB` : ''}
                        </span>
                      )}
                    </button>
          );
        })}
      </div>

      {open && openIdx != null && (
        <div
          className="media-lightbox"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={close}
        >
          <div className="media-lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <div className="media-lightbox-bar">
              <span id={titleId} className="media-lightbox-title">
                {open.alt || open.path || open.id || 'Image'}
                {images.length > 1 ? ` · ${openIdx + 1}/${images.length}` : ''}
              </span>
              <button type="button" className="btn btn-sm" onClick={close} aria-label="Close">
                close
              </button>
            </div>
            <img className="media-lightbox-img" src={safeSrc(open.src)!} alt={open.alt || ''} />
            {images.length > 1 && (
              <div className="media-lightbox-nav">
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setOpenIdx((openIdx - 1 + images.length) % images.length)}
                >
                  prev
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setOpenIdx((openIdx + 1) % images.length)}
                >
                  next
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Merge media lists, de-dupe by src/id. */
export function mergeMedia(...lists: Array<MediaPart[] | undefined | null>): MediaPart[] {
  const seen = new Set<string>();
  const out: MediaPart[] = [];
  for (const list of lists) {
    for (const p of list || []) {
      if (!p?.src) continue;
      const key = p.id || p.src;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }
  }
  return out;
}
