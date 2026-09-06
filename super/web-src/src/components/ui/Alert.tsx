import * as React from 'react';
import { cn } from '../../utils/cn';
type Variant = 'error' | 'warning' | 'success' | 'info';
export function Alert({ variant = 'info', className, children, ...rest }: React.HTMLAttributes<HTMLDivElement> & { variant?: Variant }) {
  return <div className={cn('alert', `alert--${variant}`, className)} role="alert" {...rest}>{children}</div>;
}
