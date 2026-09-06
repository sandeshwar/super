import * as React from 'react';
import { cn } from '../../utils/cn';

type Variant = 'default' | 'primary' | 'secondary' | 'outline' | 'ghost' | 'subtle' | 'danger';
type Size = 'sm' | 'md' | 'lg' | 'icon' | 'icon-sm';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  block?: boolean;
  loading?: boolean;
}

const variantClass: Record<Variant, string> = {
  default: 'btn',
  primary: 'btn btn-primary',
  secondary: 'btn btn-secondary',
  outline: 'btn btn-outline',
  ghost: 'btn btn-ghost',
  subtle: 'btn btn-subtle',
  danger: 'btn btn-danger',
};
const sizeClass: Record<Size, string> = {
  sm: 'btn-sm',
  md: '',
  lg: 'btn-lg',
  icon: 'btn-icon',
  'icon-sm': 'btn-icon btn-sm',
};

export function Button({ variant = 'default', size = 'md', block, loading, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={cn(variantClass[variant], sizeClass[size], block && 'btn-block', className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className="spin" style={{ width: 14, height: 14, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: 999, display: 'inline-block' }} aria-hidden />}
      {children}
    </button>
  );
}
