import type { LlmStats } from '../../types';

function fmtTps(n?: number) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return n >= 100 ? n.toFixed(0) : n.toFixed(1);
}

function fmtMs(n?: number) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`;
  return `${n.toFixed(0)}ms`;
}

/** Single-line context + decode/prefill. Visibility controlled by side toggle. */
export function ContextBar({ tokenStats, messagesLen, cost, llmStats, open, busy }: {
  tokenStats: { total: number; limit: number | null; pct: number | null };
  messagesLen: number;
  cost: { total: number } | null;
  llmStats?: LlmStats | null;
  busy?: boolean;
  open: boolean;
}) {
  if (!open) return null;

  const over = (tokenStats.pct ?? 0) > 85;
  const hasLimit = typeof tokenStats.limit === 'number' && tokenStats.limit > 0;
  const decode = fmtTps(llmStats?.decode_tps);
  const prefill = fmtTps(llmStats?.prefill_tps);
  const tPrefill = fmtMs(llmStats?.prompt_ms);
  const live = llmStats?.source === 'live' || !!busy;

  const parts: string[] = [];
  if (decode) parts.push(`decode ${decode}/s${llmStats?.source === 'live' ? '…' : ''}`);
  if (prefill) parts.push(`prefill ${prefill}/s`);
  else if (llmStats?.prefill_cached) {
    parts.push(tPrefill ? `prefill cached ${tPrefill}` : 'prefill cached');
  } else if (llmStats?.source === 'live' && llmStats.prompt_ms != null && llmStats.decode_tps == null) {
    parts.push(`prefill ${fmtMs(llmStats.prompt_ms)}…`);
  }

  if (hasLimit) {
    parts.push(
      `~${tokenStats.total.toLocaleString()} / ${tokenStats.limit!.toLocaleString()} tok est.`
      + (tokenStats.pct != null ? ` (${tokenStats.pct}%)` : ''),
    );
  } else {
    parts.push(`~${tokenStats.total.toLocaleString()} tok est.`);
  }
  parts.push(`${messagesLen} msgs`);
  if (cost) parts.push(`~${cost.total} tok`);

  return (
    <div className="context-bar" role="status" aria-label="Context">
      <div className="context-bar-line">
        {hasLimit && tokenStats.pct != null && (
          <div className="context-bar-meter" aria-hidden title={`${tokenStats.pct}% context`}>
            <div style={{
              width: `${Math.min(100, tokenStats.pct)}%`,
              height: '100%',
              background: over ? 'var(--red)' : tokenStats.pct > 60 ? 'var(--yellow)' : 'var(--accent)',
            }} />
          </div>
        )}
        <span className={`mono context-bar-text${live && (decode || prefill || llmStats?.prefill_cached) ? ' is-live' : ''}`} style={{ color: over ? 'var(--red)' : undefined }}>
          {parts.join(' · ')}
        </span>
      </div>
    </div>
  );
}
