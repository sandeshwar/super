import * as React from 'react';

/** Small circle avatar: user = accent "You", assistant = icon. Reusable. */
export function Avatar({ role }: { role: string }) {
  const base: React.CSSProperties = {
    width: 28, height: 28, borderRadius: 'var(--radius-sm)', display: 'grid', placeItems: 'center', flexShrink: 0,
    fontWeight: 700, fontSize: 'var(--text-xs)',
  };
  if (role === 'user') return <div style={{ ...base, background: 'var(--accent)', color: 'var(--accent-fg)', border: '1px solid var(--accent)' }}>You</div>;
  return (
    <div style={{ ...base, background: 'var(--bg-4)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M8 8a2.2 2.2 0 100-4.4A2.2 2.2 0 008 8zM3.2 13a4.8 4.8 0 019.6 0" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
    </div>
  );
}
