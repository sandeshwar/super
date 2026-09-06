import { useMemo, useState } from 'react';
import { mdToHtml } from '../utils/markdown';
import { Button } from './ui/Button';

export function Markdown({ content, gate }: { content: string; gate?: { ok: boolean; missing: string[]; checked: number } }) {
  const html = useMemo(() => mdToHtml(content), [content]);
  const [copied, setCopied] = useState(false);

  // Enhance code blocks with copy button via DOM post-process (simple)
  return (
    <div className="md" style={{ position: 'relative' }}>
      <div dangerouslySetInnerHTML={{ __html: html }} />
      {gate && gate.checked > 0 && (
        <div style={{ marginTop: 'var(--space-2)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {gate.ok ? (
            <span className="gate-pill ok">grounded · {gate.checked} checked</span>
          ) : (
            <span className="gate-pill bad">unverified: {gate.missing.join(', ')}</span>
          )}
        </div>
      )}
      <Button
        size="sm"
        variant="ghost"
        style={{ position: 'absolute', top: 0, right: 0, opacity: 0.7 }}
        onClick={async () => {
          await navigator.clipboard.writeText(content);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}
      >
        {copied ? 'copied' : 'copy'}
      </Button>
    </div>
  );
}
