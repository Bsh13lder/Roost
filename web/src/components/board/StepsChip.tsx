import { Meter } from "../../ui/Meter";
import { stepProgress } from "../tasks/progress";
import type { TaskStepOut } from "../../api/types";

export interface StepsChipProps {
  title: string; // the task's, for the button's name
  steps: readonly TaskStepOut[];
  open: boolean;
  onToggle: () => void;
}

// The steps cell (G3): a chevron, a small meter and "2/5". A click shows or hides THIS task's steps.
export function StepsChip({ title, steps, open, onToggle }: StepsChipProps) {
  const { done, total } = stepProgress(steps);
  if (total === 0) return <span className="task-row__steps" />;
  return (
    <button type="button" className="task-row__steps task-row__steps--button" aria-expanded={open}
      aria-label={`${open ? "Hide" : "Show"} the ${total} steps of ${title}`}
      title={`${done} of ${total} steps · click to ${open ? "hide" : "show"}`} onClick={onToggle}>
      <svg className={`chev${open ? " is-open" : ""}`} viewBox="0 0 10 10" aria-hidden="true" focusable="false">
        <path d="M3 1.8 6.5 5 3 8.2" />
      </svg>
      <Meter label={`${done} of ${total} steps done`} value={done} max={total} tone="accent" className="task-row__meter" />
      {done}/{total}
    </button>
  );
}
