import type { Stats } from './hooks/useAppData';

type Props = {
  stats: Stats;
  offlinePending: number;
  criticals: unknown[];
};

export function AppFooter({ stats, offlinePending, criticals }: Props) {
  return (
    <footer className="app-footer">
      <span className="stat"><span className="dot" aria-hidden /> {stats.proven}/{stats.total} proven</span>
      <span className="sep">·</span>
      <span className="stat"><span style={{ width: 6, height: 6, borderRadius: 'var(--radius-full)', background: stats.gateReject ? 'var(--yellow)' : 'var(--green)', display: 'inline-block' }} aria-hidden /> {stats.gatePass} pass · {stats.gateReject} reject</span>
      {offlinePending > 0 && (<><span className="sep">·</span><span className="stat" style={{ color: 'var(--yellow)' }}>{offlinePending} queued</span></>)}
      {criticals.length > 0 && (<><span className="sep">·</span><span className="stat" style={{ color: 'var(--red)', fontWeight: 600 }}>{criticals.length} critical{criticals.length !== 1 && 's'}</span></>)}
      <span className="right">
        <span className="mono">SUPER v1.0</span>
        <span className="sep">·</span>
        <span className="mono muted">MLX · Qwen3.8</span>
      </span>
    </footer>
  );
}
