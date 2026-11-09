import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "./cx";
import { Tooltip } from "./Tooltip";
import type { ControlSize } from "./Button";

export interface IconButtonProps extends Omit<ComponentPropsWithRef<"button">, "aria-label" | "children" | "type"> {
  label: string; // the accessible name: an icon alone says nothing
  icon: ReactNode;
  size?: ControlSize;
  variant?: "ghost" | "secondary";
  pressed?: boolean; // a toggle: sets aria-pressed
  tooltip?: boolean; // shows the label on hover and focus (default)
}

// A square button with an icon and a name (redesign P1); its tooltip says the name.
export function IconButton({
  label, icon, size = "md", variant = "ghost", pressed, tooltip = true, className, ...rest
}: IconButtonProps) {
  const button = (
    <button {...rest} type="button" aria-label={label} aria-pressed={pressed}
      className={cx("icon-btn", `icon-btn--${size}`, `icon-btn--${variant}`, className)}>
      {icon}
    </button>
  );
  return tooltip ? <Tooltip content={label}>{button}</Tooltip> : button;
}
