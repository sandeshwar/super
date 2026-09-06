import * as React from 'react';

export type IconProps = React.SVGProps<SVGSVGElement> & { size?: number };

function wrap(path: React.ReactNode, props: IconProps) {
  const { size = 16, ...rest } = props;
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden {...rest}>
      {path}
    </svg>
  );
}

export const Icons = {
  chat: (p: IconProps) => wrap(<><path d="M2.5 3.5a1 1 0 011-1h9a1 1 0 011 1v5.5a1 1 0 01-1 1H6.2l-1.9 1.9a.5.5 0 01-.8-.4V10h-1a1 1 0 01-1-1v-5.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M5 6h6M5 8h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></>, p),
  tree: (p: IconProps) => wrap(<><circle cx="8" cy="2.5" r="2" stroke="currentColor" strokeWidth="1.2"/><circle cx="3.5" cy="12.5" r="2" stroke="currentColor" strokeWidth="1.2"/><circle cx="12.5" cy="12.5" r="2" stroke="currentColor" strokeWidth="1.2"/><path d="M8 4.5v4M5 10.8l1.5-2M11 10.8L9.5 8.8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></>, p),
  approve: (p: IconProps) => wrap(<><path d="M8 14A6 6 0 108 2a6 6 0 000 12z" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></>, p),
  report: (p: IconProps) => wrap(<><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M5 11.5V8M8 11.5V5M11 11.5V7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></>, p),
  search: (p: IconProps) => wrap(<><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2"/><path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></>, p),
  plus: (p: IconProps) => wrap(<><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></>, p),
  check: (p: IconProps) => wrap(<><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></>, p),
  info: (p: IconProps) => wrap(<><circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 7v3M8 5.5h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></>, p),
  menu: (p: IconProps) => wrap(<><path d="M3 5h10M3 8h10M3 11h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></>, p),
};
