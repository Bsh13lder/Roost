import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ControlSize = "sm" | "md" | "lg";

export interface ButtonProps extends Omit<ComponentPropsWithRef<"button">, "type"> {
  variant?: ButtonVariant;
  size?: ControlSize;
  type?: "button" | "submit" | "reset";
  block?: boolean; // full width
  loading?: boolean; // disabled and aria-busy while an action runs
}

// The one button (redesign P1): base.css's .btn classes, sized by the control-height tokens.
export function Button({
  variant = "secondary", size = "md", type = "button", block = false, loading = false, disabled, className, ...rest
}: ButtonProps) {
  return (
    <button {...rest} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={cx("btn", `btn--${variant}`, `btn--${size}`, block && "btn--block", className)} />
  );
}
