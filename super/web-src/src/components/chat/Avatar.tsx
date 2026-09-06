import * as React from 'react';

/** Circle avatar: user = accent initial, assistant = glyph. Reusable. */
export function Avatar({ role }: { role: string }) {
  const base: React.CSSProperties = {
    width: 30, height: 30, borderRadius: 'var(--radius-full)', display: 'grid', placeItems: 'center', flexShrink: 0,
    fontWeight: 700, fontSize: 'var(--text-xs)', marginTop: 2,
  };
  if (role === 'user') return <div style={{ ...base, background: 'var(--accent)', color: 'var(--accent-fg)', border: '1px solid var(--accent)' }} aria-label="you">Y</div>;
  return (
    <div style={{ ...base, background: 'var(--accent-soft)', border: '1px solid var(--accent-border)', color: 'var(--accent)' }} aria-label="super">
      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 1.5l1.8 3.9 4.2.5-3.1 2.9.8 4.2-3.7-2-3.7 2 .8-4.2-3.1-2.9 4.2-.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
    </div>
  );
}
