import { useTheme } from '../hooks/useTheme';
import { Button } from './ui/Button';

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      title={`Theme: ${theme} — click to toggle`}
      className="icon-btn"
      style={{ width: 32, height: 32, padding: 0 } as React.CSSProperties}
    >
      {theme === 'dark' ? (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><circle cx="8" cy="8" r="4.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 2.5V1M8 15V13.5M2.5 8H1M15 8H13.5M3.8 3.8L2.9 2.9M13.1 13.1L12.2 12.2M3.8 12.2L2.9 13.1M13.1 2.9L12.2 3.8" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden><path d="M13.2 8.2A5.2 5.2 0 117.8 2.8 4.2 4.2 0 0013.2 8.2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
      )}
    </Button>
  );
}
