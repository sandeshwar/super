/**
 * Minimal markdown → HTML (no dep) — code blocks, inline code, bold, links.
 * Sanitizes via escape.
 */
function esc(s: string) { return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string)); }

export function mdToHtml(src: string): string {
  if (!src) return '';
  // Extract code blocks first
  const blocks: string[] = [];
  let html = src.replace(/```([a-z]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = blocks.length;
    blocks.push(`<pre><code class="mono" data-lang="${esc(lang || '')}">${esc(code.trim())}</code></pre>`);
    return `@@BLOCK${idx}@@`;
  });
  html = esc(html);
  // Restore blocks
  html = html.replace(/@@BLOCK(\d+)@@/g, (_, i) => blocks[Number(i)] || '');
  // inline code
  html = html.replace(/`([^`]+?)`/g, (_, c) => `<code>${esc(c)}</code>`);
  // bold
  html = html.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
  // links [text](url)
  html = html.replace(/\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  // line breaks
  html = html.replace(/\n/g, '<br/>');
  return html;
}

export function extractCitations(text: string): { clean: string; symbols: string[] } {
  const symbols = Array.from(text.matchAll(/`([^`]+?)`/g)).map((m) => m[1].trim()).filter(Boolean);
  return { clean: text, symbols };
}
