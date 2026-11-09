import type { ReactNode } from "react";
import { cx } from "./cx";

export interface EmptyStateProps {
  title: string;
  hint?: ReactNode;
  art?: ReactNode; // a picture (a robot), decorative
  action?: ReactNode; // a button that starts the first thing
  className?: string;
}

// What a list shows when it has nothing yet (redesign P1; P5 gives each one its robot).
export function EmptyState({ title, hint, art, action, className }: EmptyStateProps) {
  return (
    <div className={cx("empty-state", className)}>
      {art ? <div className="empty-state__art" aria-hidden="true">{art}</div> : null}
      <p className="empty-state__title">{title}</p>
      {hint ? <p className="empty-state__hint">{hint}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}
