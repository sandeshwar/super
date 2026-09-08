import type { Stats } from './hooks/useAppData';

type Props = {
  stats: Stats;
  offlinePending: number;
  criticals: unknown[];
  onDrainOffline?: () => void;
};

export function AppFooter({ stats, offlinePending, criticals, onDrainOffline }: Props) {
  return (
    <footer className="app-footer">
      <span className="stat">
        <span className="dot" style={{ background: stats.gateReject ? 'var(--yellow)' : 'var(--green)', animation: 'none' }} aria-hidden />
        {stats.gatePass} passed · {stats.gateReject} failed
      </span>
      {offlinePending > 0 && (
        <>
          <span className="sep" aria-hidden>·</span>
          <button
            type="button"
            className="stat linkish"
            style={{ color: 'var(--yellow)' }}
            onClick={onDrainOffline}
            title="Retry queued actions"
          >
            <span className="dot" style={{ background: 'var(--yellow)', animation: 'none' }} aria-hidden />
            {offlinePending} waiting to retry
          </button>
        </>
      )}
      {criticals.length > 0 && (
        <>
          <span className="sep" aria-hidden>·</span>
          <span className="stat" style={{ color: 'var(--red)' }}>
            <span className="dot" style={{ background: 'var(--red)', animation: 'none' }} aria-hidden />
            {criticals.length} open problem{criticals.length !== 1 && 's'}
          </span>
        </>
      )}
      <span className="right">
        <span className="mono">SUPER v1.0</span>
      </span>
    </footer>
  );
}
