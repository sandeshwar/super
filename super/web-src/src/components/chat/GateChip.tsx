import type { GateInfo } from '../../types';

export function GateChip({ gate }: { gate?: GateInfo }) {
  if (!gate) return null;
  if (gate.checked === 0) return <span className="gate-pill muted">no symbols</span>;
  return gate.ok ? (
    <span className="gate-pill ok">grounded · {gate.checked} checked</span>
  ) : (
    <span className="gate-pill bad">unverified · {gate.missing.slice(0, 3).join(', ')}{gate.missing.length > 3 ? ` +${gate.missing.length - 3}` : ''}</span>
  );
}
