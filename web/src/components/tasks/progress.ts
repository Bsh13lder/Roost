import type { TaskStepOut } from "../../api/types";

// A task's steps done out of all of them (redesign P3): the row's chip and the drawer's bar.
export interface StepProgress {
  done: number;
  total: number;
}

export function stepProgress(steps: readonly TaskStepOut[]): StepProgress {
  return { done: steps.filter((step) => step.done).length, total: steps.length };
}

/** "2/5 steps", or null for a task with no steps. */
export function stepsText(steps: readonly TaskStepOut[]): string | null {
  const { done, total } = stepProgress(steps);
  return total === 0 ? null : `${done}/${total} steps`;
}
