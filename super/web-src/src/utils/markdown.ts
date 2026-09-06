/**
 * Minimal markdown → HTML (no dep): code blocks, headings, lists,
 * blockquotes, tables, hr, inline code, bold, italic, links.
 * Sanitizes via escape.
 */
function esc(s: string) { return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string)); }

function inline(s: string): string {
  let html = esc(s);
  // inline code (must run before other inline rules)
  html = html.replace(/`([^`]+?)`/g, (_, c) => `<code>${esc(c)}</code>`);
  // bold + italic
  html = html.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^*\w])\*([^*\n]+?)\*/g, '$1<em>$2</em>');
  // links [text](url)
  html = html.replace(/\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return html;
}

function isTableDelim(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|[\s:|.-]*$/.test(line) && line.includes('|') && /-/.test(line);
}

function splitRow(line: string): string[] {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|')) t = t.slice(0, -1);
  return t.split('|').map((c) => c.trim());
}

export function mdToHtml(src: string): string {
  if (!src) return '';
  // Extract fenced code blocks first
  const blocks: string[] = [];
  const text = src.replace(/```([a-z]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const idx = blocks.length;
    blocks.push(`<pre><code class="mono"${lang ? ` data-lang="${esc(lang)}"` : ''}>${esc((code as string).trim())}</code></pre>`);
    return `@@BLOCK${idx}@@`;
  });

  const lines = text.split('\n');
  const out: string[] = [];
  let i = 0;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.map(inline).join('<br/>')}</p>`);
      para = [];
    }
  };

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();

    if (/^@@BLOCK\d+@@$/.test(t)) { flushPara(); out.push(t); i++; continue; }
    if (!t) { flushPara(); i++; continue; }
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(t)) { flushPara(); out.push('<hr/>'); i++; continue; }

    const h = t.match(/^(#{1,4})\s+(.+)$/);
    if (h) { flushPara(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }

    if (/^&gt;/.test(esc(t)) || t.startsWith('>')) {
      flushPara();
      const quotes: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quotes.push(lines[i].trim().replace(/^>\s?/, ''));
        i++;
      }
      out.push(`<blockquote>${quotes.map(inline).join('<br/>')}</blockquote>`);
      continue;
    }

    if (/^([-*+]|\d+[.)])\s+\S/.test(t)) {
      flushPara();
      const ordered = /^\d+[.)]/.test(t);
      const items: string[] = [];
      while (i < lines.length && /^([-*+]|\d+[.)])\s+\S/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^([-*+]|\d+[.)])\s+/, ''));
        i++;
      }
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${items.map((it) => `<li>${inline(it)}</li>`).join('')}</${tag}>`);
      continue;
    }

    // pipe table: header + delim + rows
    if (t.includes('|') && i + 1 < lines.length && isTableDelim(lines[i + 1])) {
      flushPara();
      const head = splitRow(t);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push(`<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${
        rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')
      }</tbody></table>`);
      continue;
    }

    para.push(line);
    i++;
  }
  flushPara();

  let html = out.join('\n');
  html = html.replace(/@@BLOCK(\d+)@@/g, (_, n) => blocks[Number(n)] || '');
  return html;
}

export function extractCitations(text: string): { clean: string; symbols: string[] } {
  const symbols = Array.from(text.matchAll(/`([^`]+?)`/g)).map((m) => m[1].trim()).filter(Boolean);
  return { clean: text, symbols };
}
