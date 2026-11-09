import { describeError } from "../../api/client";
import { updateStep } from "../../api/tasks";
import type { TaskStepOut } from "../../api/types";
import { useToast } from "../../ui/Toast";

export interface SubStepsProps {
  taskId: string;
  title: string;
  steps: readonly TaskStepOut[];
  onSteps: (taskId: string, steps: readonly TaskStepOut[]) => void;
}

// One task's steps under its row (G3), each with its own tick. A tick shows at once and is written through
// the step route; a failure puts the old steps back and says why. Nothing is changed in place.
export function SubSteps({ taskId, title, steps, onSteps }: SubStepsProps) {
  const toast = useToast();
  const tick = async (step: TaskStepOut) => {
    const before = steps;
    const done = !step.done;
    onSteps(taskId, before.map((s) => (s.id === step.id ? { ...s, done } : s)));
    try {
      const saved = await updateStep(taskId, step.id, { done });
      onSteps(taskId, saved.steps);
    } catch (err) {
      onSteps(taskId, before);
      toast.show(describeError(err), { tone: "danger" });
    }
  };
  return (
    <div className="substeps" role="group" aria-label={`Steps of ${title}`}>
      {steps.map((step) => (
        <div key={step.id} className={`sub${step.done ? " is-done" : ""}`}>
          <button type="button" role="checkbox" aria-checked={step.done} className={`check${step.done ? " is-done" : ""}`}
            aria-label={`${step.done ? "Reopen" : "Complete"} step ${step.title}`} onClick={() => void tick(step)} />
          <span className="t">{step.title}</span>
        </div>
      ))}
    </div>
  );
}
