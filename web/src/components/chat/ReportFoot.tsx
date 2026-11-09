import type { ReactNode } from "react";
import { WebMark } from "./WebMark";

export const REMINDER_FOOT = "🔔 Reminder";

// The quiet grey line under a Report's bubble (owner, 2026-10-26: "like Grok"): where it came from, a small link or
// two, and the web mark.
export function ReportFoot({ label, tainted, children }: { label: string | null; tainted: boolean; children?: ReactNode }) {
  if (!label && !children && !tainted) return null;
  return (
    <div className="report__foot">
      {label ? <span className="report__foot-name">{label}</span> : null}
      {children}
      {tainted ? <WebMark className="message__taint" /> : null}
    </div>
  );
}
