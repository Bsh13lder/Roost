import type { ReactNode } from "react";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode; // its label
  disabled?: boolean;
  title?: string;
}

// An on/off setting (Board redesign G6, such as Split by project): a button with role "switch", so a screen
// reader hears its state. Click and Space (the button's own) toggle it; a disabled one does nothing.
export function Switch({ checked, onChange, children, disabled = false, title }: SwitchProps) {
  return (
    <button type="button" role="switch" className="sw" aria-checked={checked} disabled={disabled} title={title}
      onClick={() => onChange(!checked)}>
      <span className="sw__track" aria-hidden="true" />
      {children}
    </button>
  );
}
