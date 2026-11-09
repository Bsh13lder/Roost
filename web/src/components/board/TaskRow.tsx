import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import { FromLazyClawMark } from "./FromLazyClawMark";
import { MadeByChip } from "./MadeByChip";
import { formatMoneyShort } from "./money";
import { PriorityMark } from "./PriorityMark";
import { ReschedulePopover, type DuePick } from "./ReschedulePopover";
import { StepsChip } from "./StepsChip";
import { useLongPress } from "./useLongPress";
import { SubSteps } from "./SubSteps";
import { dueTone, dueWords } from "./taskChips";
import { WebContentChip } from "./WebContentChip";
import { MoreIcon } from "../icons";
import type { TaskRowOut } from "../../api/tasks";
import type { TaskStepOut } from "../../api/types";
import { Menu, MenuItem } from "../../ui/Menu";
import { cx } from "../../ui/cx";
import { dueParts, todayIn } from "../../ui/date/dates";

export interface TaskRowProps {
  task: TaskRowOut;
  showProject: boolean; // false on a project's own page
  project?: { name: string; color: string };
  stepsOpen: boolean;
  onToggleSteps: (id: string) => void;
  cursor: boolean; // the keyboard cursor is on this row
  onComplete: (task: TaskRowOut) => void;
  onOpen: (id: string) => void;
  onFail: (id: string) => void;
  onKeep: (id: string) => void;
  onReschedule: (task: TaskRowOut, pick: DuePick) => void;
  onSteps?: (id: string, steps: readonly TaskStepOut[]) => void; // a ticked step, for the parent's copy
  onMove?: (task: TaskRowOut) => void; // the Workspace: Move to another project
  onDelete?: (task: TaskRowOut) => void; // the Workspace: Delete, with Undo
}

const OPEN: ReadonlySet<TaskRowOut["status"]> = new Set(["todo", "in_progress"]);
const NOTHING = () => undefined;

// "€80 left" or "€30 over", from the server's numbers; the tooltip says what was spent of what.
function MoneyCell({ money }: { money: TaskRowOut["money"] }) {
  if (!money) return <span className="task-row__money" />;
  const { currency } = money;
  const text = money.over ? `${formatMoneyShort(money.left.replace("-", ""), currency)} over`
    : `${formatMoneyShort(money.left, currency)} left`;
  return (
    <span className={cx("task-row__money", money.over && "task-row__money--over")}
      title={`${formatMoneyShort(money.spent, currency)} spent of ${formatMoneyShort(money.planned, currency)}`}>{text}</span>
  );
}

// The task's project as a pill that opens the project's page (app restructure: Workspace).
// The phone's meta line repeats it as plain words (`plain`): that line is hidden from assistive tech.
function ProjectCell({ project, id, plain = false }: { project?: TaskRowProps["project"]; id: string | null; plain?: boolean }) {
  if (!project) return <span className="task-row__project" />;
  if (plain || !id) {
    return (
      <span className="task-row__project project-pill">
        <span className="dot" style={{ background: project.color }} aria-hidden="true" />
        <span className="n">{project.name}</span>
      </span>
    );
  }
  return (
    <Link to={`/board/projects/${encodeURIComponent(id)}`} className="task-row__project project-pill" aria-label={project.name}>
      <span className="dot" style={{ background: project.color }} aria-hidden="true" />
      <span className="n">{project.name}</span>
    </Link>
  );
}

// One task as one line (G3): tick, title with its priority mark, steps, money, project, due, actions. A click
// anywhere on the row opens the drawer unless it hit a button. Steps open inline under the row.
export function TaskRow({
  task, showProject, project, stepsOpen, onToggleSteps, cursor, onComplete, onOpen, onFail, onKeep, onReschedule,
  onSteps = NOTHING, onMove, onDelete,
}: TaskRowProps) {
  const [moving, setMoving] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const press = useLongPress(() => setMenuOpen(true));
  const line = useRef<HTMLDivElement>(null);
  useEffect(() => { if (cursor) line.current?.scrollIntoView?.({ block: "nearest" }); }, [cursor]);
  const open = OPEN.has(task.status);
  const today = todayIn();
  const words = dueWords(task.due_date, today, !open);
  const tone = open ? dueTone(task.due_date, today) : "later";
  const shownProject = showProject ? project : undefined;
  const parts = task.due_date ? dueParts(task.due_date) : null;
  // A click in a menu or popover bubbles through React's tree though it sits elsewhere in the page: only
  // clicks inside the row itself, and not on a control, open the drawer.
  const rowClick = (event: MouseEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    if (press.consumed()) return; // the click that ends a long press
    if (event.currentTarget.contains(target) && !target.closest("button, a, input")) onOpen(task.id);
  };
  return (
    <>
      <div role="row" ref={line} tabIndex={-1} onClick={rowClick} data-task-id={task.id} {...press.handlers}
        className={cx("task-row", !open && "is-done", open && task.priority === "urgent" && "task-row--urgent",
          cursor && "is-cursor")}>
        <span role="gridcell" className="task-row__cell task-row__cell--check">
          <button type="button" role="checkbox" aria-checked={!open} disabled={!open}
            className={cx("check", !open && "is-done")} aria-label={`Complete ${task.title}`}
            onClick={() => onComplete(task)} />
        </span>
        <span role="gridcell" className="task-row__title">
          <PriorityMark priority={task.priority} />
          <button type="button" className="task-row__open" onClick={() => onOpen(task.id)}>
            <span className="t">{task.title}</span>
          </button>
          {task.recurring ? <span className="task-row__quiet" title={task.repeat_text ?? "Repeats"}>↻</span> : null}
          {task.starred ? <span className="task-row__star" role="img" aria-label="Starred">★</span> : null}
          <MadeByChip botId={task.created_by_bot} />
          <FromLazyClawMark from={task.imported_from} />
          {task.tainted ? <WebContentChip what={task.title} onKeep={() => onKeep(task.id)} /> : null}
        </span>
        <span role="gridcell" className="task-row__cell task-row__cell--steps">
          <StepsChip title={task.title} steps={task.steps} open={stepsOpen} onToggle={() => onToggleSteps(task.id)} />
        </span>
        <span role="gridcell" className="task-row__cell task-row__cell--money"><MoneyCell money={task.money} /></span>
        <span role="gridcell" className="task-row__cell task-row__cell--project"><ProjectCell project={shownProject} id={task.project_id} /></span>
        <span role="gridcell" className={cx("task-row__cell", "task-row__due", `task-row__due--${tone}`)}>{words}</span>
        <span role="gridcell" className="task-row__actions">
          <ReschedulePopover title={`Reschedule “${task.title}”`} open={moving} onOpenChange={setMoving}
            current={parts ? { day: parts.day, time: parts.time } : null}
            onPick={(pick) => onReschedule(task, pick)}
            trigger={<button type="button" className="icon-btn" title="Reschedule" aria-label={`Reschedule ${task.title}`}>→</button>} />
          <Menu label={`More for ${task.title}`} trigger={<MoreIcon />} open={menuOpen} onOpenChange={setMenuOpen}>
            {open ? <MenuItem onSelect={() => setMoving(true)}>Reschedule…</MenuItem> : null}
            {onMove ? <MenuItem onSelect={() => onMove(task)}>Move to…</MenuItem> : null}
            {open ? <MenuItem onSelect={() => onComplete(task)}>Mark done</MenuItem> : null}
            <MenuItem onSelect={() => onOpen(task.id)}>Open</MenuItem>
            {open ? <MenuItem onSelect={() => onFail(task.id)}>Mark failed</MenuItem> : null}
            {onDelete ? <MenuItem danger onSelect={() => onDelete(task)}>Delete</MenuItem> : null}
          </Menu>
        </span>
        <span className="row__meta" aria-hidden="true">
          <ProjectCell project={shownProject} id={task.project_id} plain />
          {task.steps.length > 0 ? <span>{task.steps.filter((s) => s.done).length}/{task.steps.length}</span> : null}
          <MoneyCell money={task.money} />
        </span>
      </div>
      {stepsOpen && task.steps.length > 0 ? (
        <SubSteps taskId={task.id} title={task.title} steps={task.steps} onSteps={onSteps} />
      ) : null}
    </>
  );
}
