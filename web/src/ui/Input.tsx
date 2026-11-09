import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import type { ControlSize } from "./Button";

export interface InputProps extends Omit<ComponentPropsWithRef<"input">, "size"> {
  controlSize?: ControlSize; // "size" is the native attribute's name, so the height is controlSize
  invalid?: boolean;
}

// A text box (redesign P1). Inside a Field it takes the Field's id, hint and error.
export function Input({ controlSize = "lg", invalid, id, className, "aria-describedby": describedBy, ...rest }: InputProps) {
  const a11y = controlA11y(useFieldControl(), { id, describedBy, invalid });
  return <input {...rest} {...a11y} className={cx("input", `input--${controlSize}`, className)} />;
}
