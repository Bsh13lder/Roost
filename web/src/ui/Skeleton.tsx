import { cx } from "./cx";

export interface SkeletonProps {
  lines?: number; // how many grey bars
  label?: string; // what is loading, for screen readers
  className?: string;
}

// Grey bars where content will be (redesign P1). One status for the whole group; the bars are hidden.
export function Skeleton({ lines = 1, label = "Loading", className }: SkeletonProps) {
  return (
    <div className={cx("skeleton-group", className)} role="status" aria-label={label}>
      {Array.from({ length: Math.max(lines, 1) }, (_, index) => (
        <span key={index} className="skeleton" aria-hidden="true" />
      ))}
    </div>
  );
}
