import { railGroups } from "./rail/railGroups";
import type { TaskRowOut } from "../../api/tasks";
import type { ProjectOut } from "../../api/types";
import { Sheet } from "../../ui/Sheet";
import { cx } from "../../ui/cx";

export interface MoveToSheetProps {
  task: TaskRowOut | null; // the task being moved; null: closed
  projects: readonly ProjectOut[];
  onPick: (task: TaskRowOut, projectId: string | null, name: string) => void;
  onClose: () => void;
}

const NO_PROJECT_NAME = "No project";

// "Move “…” to…": the live projects (pinned first) and No project; the task's own is marked and does nothing.
export function MoveToSheet({ task, projects, onPick, onClose }: MoveToSheetProps) {
  const groups = railGroups(projects);
  const places = [...groups.pinned, ...groups.active].map((project) => ({ id: project.id as string | null, name: project.name, color: project.color }));
  const all = [...places, { id: null, name: NO_PROJECT_NAME, color: undefined }];
  return (
    <Sheet open={task !== null} onOpenChange={(open) => { if (!open) onClose(); }} title={task ? `Move “${task.title}” to…` : "Move to…"}>
      {task ? (
        <ul className="move-to">
          {all.map((place) => {
            const here = place.id === task.project_id;
            return (
              <li key={place.id ?? "none"}>
                <button type="button" className={cx("move-to__item", here && "is-current")} aria-current={here ? "true" : undefined}
                  onClick={() => { onClose(); if (!here) onPick(task, place.id, place.name); }}>
                  {place.color ? <span className="project-dot" style={{ background: place.color }} aria-hidden="true" /> : null}
                  {place.name}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </Sheet>
  );
}
