import { useState, type CSSProperties, type ReactNode } from 'react';
import { cn } from '../../utils/cn';

type Props = {
  title: ReactNode;
  meta?: ReactNode;
  badge?: ReactNode;
  defaultOpen?: boolean;
  /** Controlled open state (takes precedence over defaultOpen). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Animate expand/collapse via grid-template-rows instead of mount/unmount. */
  animated?: boolean;
  /** persist open state across reloads */
  storageKey?: string;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  compact?: boolean;
};

/**
 * Collapsible — single-responsibility disclosure section.
 * Token-first flat styling; chevron rotates on open.
 * Pass storageKey to persist across reloads (sidebar/panels).
 */
export function Collapsible({
  title, meta, badge, defaultOpen = true, open: openProp, onOpenChange,
  animated, storageKey, children, className, style, compact,
}: Props) {
  const controlled = openProp !== undefined;
  const [uncontrolled, setUncontrolled] = useState<boolean>(() => {
    if (!storageKey) return defaultOpen;
    try {
      const v = localStorage.getItem(`super_collapse_${storageKey}`);
      return v === null ? defaultOpen : v === '1';
    } catch {
      return defaultOpen;
    }
  });
  const open = controlled ? Boolean(openProp) : uncontrolled;

  const toggle = () => {
    const n = !open;
    if (!controlled) {
      setUncontrolled(n);
      if (storageKey) {
        try { localStorage.setItem(`super_collapse_${storageKey}`, n ? '1' : '0'); } catch { /* ignore */ }
      }
    }
    onOpenChange?.(n);
  };

  return (
    <section className={cn('collapsible', !open && 'collapsed', compact && 'collapsible-compact', animated && 'collapsible-animated', className)} style={style}>
      <button
        type="button"
        className="collapsible-head"
        onClick={toggle}
        aria-expanded={open}
      >
        <svg
          className="collapsible-chevron"
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden
        >
          <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="collapsible-title">{title}</span>
        {badge}
        {meta && <span className="collapsible-meta">{meta}</span>}
      </button>
      {animated ? (
        <div className={cn('collapsible-panel', open && 'is-open')}>
          <div className="collapsible-panel-inner">
            <div className="collapsible-body">{children}</div>
          </div>
        </div>
      ) : (
        open && <div className="collapsible-body">{children}</div>
      )}
    </section>
  );
}
