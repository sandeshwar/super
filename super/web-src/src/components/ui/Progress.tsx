import * as React from 'react';
import { cn } from '../../utils/cn';

export function Progress({ value, max = 100, variant, className, ...rest }: { value: number; max?: number; variant?: 'default' | 'success' | 'warning'; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  const pct = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const v = variant === 'success' ? 'progress--success' : variant === 'warning' ? 'progress--warning' : '';
  return (
    <div className={cn('progress', v, className)} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} {...rest}>
      <i style={{ width: `${pct}%` }} />
    </div>
  );
}
