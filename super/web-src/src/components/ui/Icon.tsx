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
  settings: (p: IconProps) => wrap(<><circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.2"/><path d="M8 1.8v1.4M8 12.8v1.4M1.8 8h1.4M12.8 8h1.4M3.2 3.2l1 1M11.8 11.8l1 1M3.2 12.8l1-1M11.8 4.2l1-1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></>, p),
  search: (p: IconProps) => wrap(<><circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.2"/><path d="M10 10l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></>, p),
  plus: (p: IconProps) => wrap(<><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></>, p),
  check: (p: IconProps) => wrap(<><path d="M5.5 8l1.8 1.8L10.8 6.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></>, p),
  info: (p: IconProps) => wrap(<><circle cx="8" cy="8" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 7v3M8 5.5h.01" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></>, p),
  menu: (p: IconProps) => wrap(<><path d="M3 5h10M3 8h10M3 11h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></>, p),
  tools: (p: IconProps) => wrap(<><path d="M10.2 2.8a2.2 2.2 0 013 3L9.5 9.5l-1.2.2.2-1.2 3.7-3.7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/><path d="M2.5 13.5l3.8-3.8M8.2 7.8L5.5 5.1a2 2 0 00-2.8 0L2 5.8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></>, p),
  terminal: (p: IconProps) => wrap(<><rect x="2" y="2.5" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M5 6.2l2.2 1.8L5 9.8M8.2 9.8H11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></>, p),
  panelRight: (p: IconProps) => wrap(<><rect x="2" y="2.5" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M10 2.5v11" stroke="currentColor" strokeWidth="1.2"/></>, p),
  activity: (p: IconProps) => wrap(<><path d="M1.5 8h2.2l1.6-4.2L8 12.5l1.8-4.5H14.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></>, p),
};
