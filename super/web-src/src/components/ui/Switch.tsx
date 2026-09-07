import { cn } from '../../utils/cn';

type Props = {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  id?: string;
  label?: string;
  description?: string;
};

export function Switch({ checked, onChange, disabled, id, label, description }: Props) {
  const control = (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={cn('switch', checked && 'on')}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-thumb" aria-hidden />
    </button>
  );
  if (!label) return control;
  return (
    <label className={cn('switch-row', disabled && 'disabled')} htmlFor={id}>
      <span className="switch-copy">
        <span className="switch-label">{label}</span>
        {description && <span className="switch-desc">{description}</span>}
      </span>
      {control}
    </label>
  );
}
