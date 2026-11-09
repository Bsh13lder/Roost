import type { TaskGroup } from "./groupTasks";
import { ReschedulePopover, type DuePick } from "./ReschedulePopover";
import { TaskRow, type TaskRowProps } from "./TaskRow";
import type { TaskRowOut } from "../../api/tasks";
import { Button } from "../../ui/Button";

export interface TaskGroupsProps {
  groups: readonly TaskGroup[];
  cursor: number; // the keyboard cursor's place in the rows as shown, flat
  showProject: boolean;
  projects: ReadonlyMap<string, { name: string; color: string }>;
  stepsOpen: ReadonlySet<string>;
  canRescheduleAll: boolean;
  onRescheduleAll: (pick: DuePick) => void;
  row: Pick<TaskRowProps, "onToggleSteps" | "onComplete" | "onOpen" | "onFail" | "onKeep" | "onReschedule" | "onSteps"
    | "onMove" | "onDelete">;
}

// Each group is a heading row (its title, its count, a hairline) over its rows. Every row gets its flat index,
// so the cursor runs through the groups in the order they are drawn.
export function TaskGroups({ groups, cursor, showProject, projects, stepsOpen, canRescheduleAll, onRescheduleAll, row }: TaskGroupsProps) {
  let next = 0;
  return (
    <>
      {groups.map((group) => {
        const first = next;
        next += group.rows.length;
        return (
          <section key={group.key} className="group" aria-label={group.title}>
            <div className="group__head">
              <h3 className={`group__title${group.tone === "danger" ? " danger" : ""}`}>{group.title}</h3>
              <span className="count">{group.rows.length}</span>
              {group.action === "reschedule-all" && canRescheduleAll ? (
                <ReschedulePopover title={`Reschedule ${group.rows.length} overdue task${group.rows.length === 1 ? "" : "s"}`}
                  current={null} onPick={onRescheduleAll}
                  trigger={<Button size="sm" variant="ghost">Reschedule all</Button>} />
              ) : null}
            </div>
            <div role="grid" aria-label={group.title} className="task-list">
              {group.rows.map((task: TaskRowOut, index) => (
                <TaskRow key={task.id} task={task} showProject={showProject}
                  project={task.project_id ? projects.get(task.project_id) : undefined}
                  stepsOpen={stepsOpen.has(task.id)} cursor={first + index === cursor} {...row} />
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
