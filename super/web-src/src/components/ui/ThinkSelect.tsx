import { THINK_LEVEL_LABELS, type ThinkLevel } from '../../lib/think';

type Props = {
  value: ThinkLevel;
  levels: ThinkLevel[];
  disabled?: boolean;
  compact?: boolean;
  id?: string;
  onChange: (level: ThinkLevel) => void;
};

export function ThinkSelect({ value, levels, disabled, compact, id, onChange }: Props) {
  if (!levels.length || (levels.length === 1 && levels[0] === 'off')) {
    return null;
  }
  const safe = levels.includes(value) ? value : (levels.find((l) => l !== 'off') || levels[0]);
  return (
    <select
      id={id}
      value={safe}
      disabled={disabled}
      aria-label="Thinking level"
      title="Thinking / reasoning effort"
      onChange={(e) => onChange(e.target.value as ThinkLevel)}
      className={compact ? 'header-think-select' : 'input'}
      style={compact ? undefined : { maxWidth: 220 }}
    >
      {levels.map((l) => (
        <option key={l} value={l}>{THINK_LEVEL_LABELS[l] || l}</option>
      ))}
    </select>
  );
}
