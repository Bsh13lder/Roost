import type { ReactNode } from "react";
import { cx } from "./cx";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "danger" | "info";

export interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}

// A small label that never acts: a count, a state, a mark (redesign P1).
export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return <span className={cx("badge", `badge--${tone}`, className)}>{children}</span>;
}
