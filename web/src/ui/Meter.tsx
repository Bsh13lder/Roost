import { cx } from "./cx";

export type MeterTone = "accent" | "ok" | "warn" | "over";

export interface MeterProps {
  label: string; // the meter's accessible name
  value: number; // drawn and announced clamped to 0..max
  max?: number;
  tone?: MeterTone;
  valueText?: string; // what a screen reader says instead of the number
  className?: string;
}

const FULL = 100;

// A bar for an amount of something, a budget for one (redesign P1). The caller sends the tone.
export function Meter({ label, value, max = FULL, tone = "accent", valueText, className }: MeterProps) {
  const shown = Math.min(Math.max(value, 0), max);
  const percent = max > 0 ? (shown / max) * FULL : 0;
  return (
    <div className={cx("meter", className)} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max}
      aria-valuenow={shown} aria-valuetext={valueText}>
      <div className={cx("meter__fill", `meter__fill--${tone}`)} style={{ width: `${percent}%` }} />
    </div>
  );
}
