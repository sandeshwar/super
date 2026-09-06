import { Button } from '../ui/Button';

export function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-3)', color: 'var(--fg-3)', textAlign: 'center', padding: 'var(--space-6) 0' }}>
      <div style={{ width: 52, height: 52, borderRadius: 'var(--radius-lg)', background: 'var(--accent)', display: 'grid', placeItems: 'center', color: 'var(--accent-fg)', border: '1px solid var(--accent)' }}>
        <svg width="22" height="22" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M2.5 3.5a1 1 0 011-1h9a1 1 0 011 1v5.5a1 1 0 01-1 1H6.2l-1.9 1.9a.5.5 0 01-.8-.4V10h-1a1 1 0 01-1-1v-5.5z" stroke="currentColor" strokeWidth="1.2"/></svg>
      </div>
      <div>
        <div style={{ fontWeight: 600, fontSize: 'var(--text-md)', color: 'var(--fg-1)' }}>Grounded by default</div>
        <div style={{ fontSize: 'var(--text-sm)', maxWidth: 420, lineHeight: 'var(--leading-normal)', marginTop: 6 }}>The model sees your current leaf task + verified memory. Backticked symbols are checked — chat warns, write gate blocks. Try <code>/add-task</code> or <code>@os.path</code></div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', justifyContent: 'center', marginTop: 4 }}>
        {['What\'s the next leaf task?', 'Show gate status', 'How is memory compiled?'].map((s) => (
          <Button key={s} size="sm" variant="default" onClick={() => onPick(s)}>{s}</Button>
        ))}
      </div>
    </div>
  );
}
