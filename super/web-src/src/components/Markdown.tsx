import { useMemo, useState } from 'react';
import { mdToHtml } from '../utils/markdown';
import { Button } from './ui/Button';

export function Markdown({ content }: { content: string }) {
  const html = useMemo(() => mdToHtml(content), [content]);
  const [copied, setCopied] = useState(false);

  // Verdict chips live in GateChip + Tool trace; rendered text stays clean.
  return (
    <div className="md md-copy-wrap" style={{ position: 'relative' }}>
      <div dangerouslySetInnerHTML={{ __html: html }} />
      <Button
        size="sm"
        variant="ghost"
        className="md-copy"
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
