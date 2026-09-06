import type { TaskNode } from '../../types';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export function LeafBanner({ leaf, leafRendered }: { leaf: TaskNode | null; leafRendered: string }) {
  if (!leaf) return null;
  return (
    <div style={{ padding: 'var(--space-2) var(--space-3)', borderBottom: '1px solid var(--border-subtle)', background: 'var(--accent-soft)', display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
      <Badge variant="accent" style={{ fontSize: 'var(--text-2xs)' }}>LEAF {leaf.id}</Badge>
      <span className="truncate" style={{ flex: 1, fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--accent)' }}>{leaf.title}</span>
      <span className="mono small muted" style={{ fontSize: 'var(--text-2xs)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{leaf.done?.slice(0, 40) || 'no done'}</span>
      <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(leafRendered)}>copy leaf</Button>
    </div>
  );
}
