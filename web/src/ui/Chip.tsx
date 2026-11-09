import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";

export interface ChipProps extends Omit<ComponentPropsWithRef<"button">, "type"> {
  selected?: boolean; // a toggle chip: aria-pressed
  size?: "sm" | "md";
}

// A small pill button: a quick pick, a filter, a time (redesign P1).
export function Chip({ selected, size = "md", className, ...rest }: ChipProps) {
  return <button {...rest} type="button" aria-pressed={selected} className={cx("chip", `chip--${size}`, className)} />;
}
