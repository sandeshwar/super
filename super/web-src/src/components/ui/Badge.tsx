import * as React from 'react';
import { cn } from '../../utils/cn';

type BadgeVariant = 'neutral' | 'accent' | 'proven' | 'waiting' | 'doing' | 'blocked' | 'success' | 'warning' | 'danger';
export function Badge({ variant = 'neutral', className, children, ...rest }: React.HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  // map semantic aliases
  const v = variant === 'success' ? 'proven' : variant === 'warning' ? 'waiting' : variant === 'danger' ? 'blocked' : variant;
  return <span className={cn('badge', v, className)} {...rest}>{children}</span>;
}
export function Dot({ className, ...rest }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('badge-dot', className)} {...rest} />;
}
