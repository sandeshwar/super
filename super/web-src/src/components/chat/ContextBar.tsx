import type { TaskNode } from '../../types';
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

/** Single-line context + provider timing. Visibility controlled by side toggle. */
export function ContextBar({ tokenStats, leaf, messagesLen, cost, llmStats, open, busy }: {
  tokenStats: { total: number; limit: number | null; pct: number | null };
  leaf: TaskNode | null;
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
  const live = llmStats?.source === 'live' || !!busy;

  const parts: string[] = [];
  // Live throughput first so it stays visible while streaming.
  if (decode) parts.push(`decode ${decode}/s${llmStats?.source === 'live' ? '…' : ''}`);
  if (prefill) parts.push(`prefill ${prefill}/s`);
  else if (llmStats?.source === 'live' && llmStats.prompt_ms != null && llmStats.decode_tps == null) {
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
  if (leaf?.id) parts.push(`task ${leaf.id}`);
  if (cost) parts.push(`~${cost.total} tok`);

  if (llmStats?.step != null) parts.push(`step ${llmStats.step}`);
  if (llmStats?.prompt_tokens != null) parts.push(`prompt ${llmStats.prompt_tokens.toLocaleString()}`);
  if (llmStats?.completion_tokens != null) parts.push(`out ${llmStats.completion_tokens.toLocaleString()}`);
  if (llmStats?.cached_tokens != null) parts.push(`cache ${llmStats.cached_tokens.toLocaleString()}`);

  const tLoad = fmtMs(llmStats?.load_ms);
  const tPrefill = fmtMs(llmStats?.prompt_ms);
  const tDecode = fmtMs(llmStats?.eval_ms);
  const tTotal = fmtMs(llmStats?.total_ms);
  if (tLoad) parts.push(`load ${tLoad}`);
  // Avoid duplicating the live "prefill Xs…" already shown above.
  if (tPrefill && !(llmStats?.source === 'live' && llmStats.decode_tps == null)) {
    parts.push(`prefill ${tPrefill}`);
  }
  if (tDecode) parts.push(`decode ${tDecode}`);
  if (tTotal) parts.push(`total ${tTotal}`);

  if (llmStats?.done_reason) parts.push(llmStats.done_reason);
  if (llmStats?.source) parts.push(llmStats.source);
  else if (live) parts.push('live');

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
        <span className={`mono context-bar-text${llmStats?.source === 'live' ? ' is-live' : ''}`} style={{ color: over ? 'var(--red)' : undefined }}>
          {parts.join(' · ')}
        </span>
      </div>
    </div>
  );
}
