import type { TaskNode } from '../../types';
import type { LlmStats } from '../../types';
import { Collapsible } from '../ui/Collapsible';

function fmtTps(n?: number) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return n >= 100 ? n.toFixed(0) : n.toFixed(1);
}

function fmtMs(n?: number) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  if (n >= 1000) return `${(n / 1000).toFixed(2)}s`;
  return `${n.toFixed(0)}ms`;
}

/** Slim context + provider timing (prefill / decode TPS). */
export function ContextBar({ tokenStats, leaf, messagesLen, cost, llmStats }: {
  tokenStats: { total: number; limit: number | null; pct: number | null };
  leaf: TaskNode | null;
  messagesLen: number;
  cost: { total: number } | null;
  llmStats?: LlmStats | null;
  busy?: boolean;
}) {
  const over = (tokenStats.pct ?? 0) > 85;
  const hasLimit = typeof tokenStats.limit === 'number' && tokenStats.limit > 0;
  const decode = fmtTps(llmStats?.decode_tps);
  const prefill = fmtTps(llmStats?.prefill_tps);
  const live = llmStats?.source === 'live';
  return (
    <div className="context-bar">
      <Collapsible
        title="Context"
        className="collapsible-bare"
        compact
        defaultOpen={false}
        storageKey="chat-context"
        meta={
          <>
            <span className="mono" style={{ color: over ? 'var(--red)' : 'var(--fg-3)' }}>
              {hasLimit && tokenStats.pct != null ? `~${tokenStats.pct}%` : 'ctx ?'}
            </span>
            {decode && (
              <span className="mono" title={live ? 'Live decode estimate' : 'Provider decode TPS'}>
                {decode} tok/s{live ? '…' : ''}
              </span>
            )}
            {prefill && !live && (
              <span className="mono" title="Provider prefill TPS">{prefill} prefill</span>
            )}
            {leaf?.id ? <span className="mono">task {leaf.id}</span> : null}
            {cost ? <span className="mono">~{cost.total} tok</span> : null}
          </>
        }
      >
        <div className="context-bar-body">
          <span className="mono">
            ~{tokenStats.total.toLocaleString()}
            {hasLimit ? ` / ${tokenStats.limit!.toLocaleString()}` : ' / —'}
            {' '}tok est.
          </span>
          {hasLimit && tokenStats.pct != null && (
            <div className="context-bar-meter" aria-hidden>
              <div style={{
                width: `${tokenStats.pct}%`,
                height: '100%',
                background: tokenStats.pct > 85 ? 'var(--red)' : tokenStats.pct > 60 ? 'var(--yellow)' : 'var(--accent)',
              }} />
            </div>
          )}
          <span className="mono">{messagesLen} msgs{leaf?.id ? ` · task ${leaf.id}` : ''}</span>
        </div>
        {llmStats && (
          <div className="context-bar-body" style={{ paddingTop: 0 }}>
            <span className="mono">
              {[
                llmStats.prompt_tokens != null ? `prompt ${llmStats.prompt_tokens}` : null,
                llmStats.completion_tokens != null ? `out ${llmStats.completion_tokens}` : null,
                llmStats.cached_tokens != null ? `cache ${llmStats.cached_tokens}` : null,
                prefill ? `prefill ${prefill}/s` : null,
                decode ? `decode ${decode}/s` : null,
                fmtMs(llmStats.prompt_ms) ? `prefill ${fmtMs(llmStats.prompt_ms)}` : null,
                fmtMs(llmStats.eval_ms) ? `decode ${fmtMs(llmStats.eval_ms)}` : null,
                fmtMs(llmStats.total_ms) ? `total ${fmtMs(llmStats.total_ms)}` : null,
              ].filter(Boolean).join(' · ')}
            </span>
            {llmStats.source && <span className="mono" style={{ color: 'var(--fg-4)' }}>{llmStats.source}</span>}
          </div>
        )}
      </Collapsible>
    </div>
  );
}
