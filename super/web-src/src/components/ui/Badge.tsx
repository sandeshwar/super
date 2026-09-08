import type { ReactNode, CSSProperties } from 'react';

type BadgeVariant = 'neutral' | 'accent' | 'success' | 'warning' | 'danger';

export function Badge({ children, variant = 'neutral', style }: { children: ReactNode; variant?: BadgeVariant; style?: CSSProperties }) {
  return <span className={`badge ${variant}`} style={style}>{children}</span>;
}
