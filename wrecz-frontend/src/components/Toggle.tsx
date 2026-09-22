type ToggleProps = {
  on: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
};

export default function Toggle({ on, onChange, label, disabled = false }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className="wrecz-toggle"
      disabled={disabled}
      onClick={() => onChange(!on)}
    >
      <span className={`wrecz-toggle-knob ${on ? "is-on" : ""}`} />
    </button>
  );
}
