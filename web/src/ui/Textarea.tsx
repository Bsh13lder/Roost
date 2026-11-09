import { useLayoutEffect, useRef, type ComponentPropsWithRef } from "react";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import { TEXTAREA_MAX_ROWS } from "./constants";

export interface TextareaProps extends Omit<ComponentPropsWithRef<"textarea">, "ref"> {
  autoGrow?: boolean; // grows with its text, up to maxRows, then scrolls
  maxRows?: number;
  invalid?: boolean;
}

// Fits the box to its text: height "auto" first, so it can also shrink, then the text's height, capped.
export function fitHeight(box: HTMLTextAreaElement, maxRows: number): void {
  const style = window.getComputedStyle(box);
  const line = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.5 || 20;
  const padding = (Number.parseFloat(style.paddingTop) || 0) + (Number.parseFloat(style.paddingBottom) || 0);
  const cap = line * maxRows + padding;
  box.style.height = "auto";
  const wanted = box.scrollHeight;
  box.style.height = `${Math.min(wanted, cap)}px`;
  box.style.overflowY = wanted > cap ? "auto" : "hidden";
}

// A multi-line box (redesign P1) that grows as you type, in every browser.
export function Textarea({
  autoGrow = true, maxRows = TEXTAREA_MAX_ROWS, invalid, id, className, value, "aria-describedby": describedBy, ...rest
}: TextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const a11y = controlA11y(useFieldControl(), { id, describedBy, invalid });
  useLayoutEffect(() => {
    if (autoGrow && ref.current) fitHeight(ref.current, maxRows);
  }, [autoGrow, maxRows, value]);
  return (
    <textarea {...rest} {...a11y} ref={ref} value={value}
      className={cx("input", "input--area", autoGrow && "input--grow", className)} />
  );
}
