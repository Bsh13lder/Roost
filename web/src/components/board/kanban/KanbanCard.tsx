import { useState, type MouseEvent } from "react";
import type { KanbanColumn } from "./kanbanGroups";
import type { CardDrag } from "./useKanbanDrag";
import { PriorityMark } from "../PriorityMark";
import { ReschedulePopover, type DuePick } from "../ReschedulePopover";
import { StepsChip } from "../StepsChip";
import { SubSteps } from "../SubSteps";
import { dueTone, dueWords } from "../taskChips";
import { MoreIcon } from "../../icons";
import { Avatar } from "../../Avatar";
import type { TaskRowOut } from "../../../api/tasks";
import type { BotOut, TaskStepOut } from "../../../api/types";
import { Menu, MenuItem, MenuNote, MenuSeparator } from "../../../ui/Menu";
import { cx } from "../../../ui/cx";
import { dueParts, todayIn } from "../../../ui/date/dates";

export interface KanbanCardProps {
  task: TaskRowOut;
  project?: { name: string; color: string };
  bot: BotOut | null; // who made it; null: you
  showWho: boolean; // hidden when the board is grouped by Bot
  moveTo: readonly KanbanColumn[]; // the other columns it can be sent to
  stepsOpen: boolean;
  dragging: boolean;
  drag: CardDrag;
  onToggleSteps: (id: string) => void;
  onSteps: (id: string, steps: readonly TaskStepOut[]) => void;
  onOpen: (id: string) => void;
  onMove: (task: TaskRowOut, key: string) => void;
  onReschedule: (task: TaskRowOut, pick: DuePick) => void;
}

const OPEN: ReadonlySet<TaskRowOut["status"]> = new Set(["todo", "in_progress"]);

function Who({ bot }: { bot: BotOut | null }) {
  if (!bot) return <span className="kcard__who kcard__who--you">You</span>;
  return (
    <span className="kcard__who">
      <Avatar avatar={bot.avatar} status={bot.status} size={16} label={false} decorative />
      {bot.name}
    </span>
  );
}

// One task as a card (G6): its priority mark and title, a ⋯ menu (Reschedule…, then Move to… with every other
// column), and a meta line: the due in words (toned), its project, the steps chip, and who made it. A click
// opens the drawer; the card drags between columns. Its steps open inside it.
export function KanbanCard({
  task, project, bot, showWho, moveTo, stepsOpen, dragging, drag, onToggleSteps, onSteps, onOpen, onMove, onReschedule,
}: KanbanCardProps) {
  const [moving, setMoving] = useState(false);
  const open = OPEN.has(task.status);
  const today = todayIn();
  const parts = task.due_date ? dueParts(task.due_date) : null;
  const words = dueWords(task.due_date, today, !open);
  const tone = open ? dueTone(task.due_date, today) : "later";
  // A click in a menu or popover bubbles through React's tree though it sits elsewhere in the page.
  const click = (event: MouseEvent<HTMLElement>) => {
    const target = event.target as HTMLElement;
    if (event.currentTarget.contains(target) && !target.closest("button, a, input")) onOpen(task.id);
  };
  return (
    <div className={cx("kcard", !open && "is-done", dragging && "is-dragging", task.priority === "urgent" && open && "kcard--urgent")}
      data-task-id={task.id} onClick={click} {...drag}>
      <div className="kcard__t">
        <PriorityMark priority={task.priority} />
        <span className="t">{task.title}</span>
        <ReschedulePopover title={`Reschedule “${task.title}”`} open={moving} onOpenChange={setMoving}
          current={parts ? { day: parts.day, time: parts.time } : null} onPick={(pick) => onReschedule(task, pick)}
          trigger={<span className="kcard__anchor" aria-hidden="true" />} />
        <Menu label={`More for ${task.title}`} trigger={<MoreIcon />}>
          {open ? <MenuItem onSelect={() => setMoving(true)}>Reschedule…</MenuItem> : null}
          {open && moveTo.length > 0 ? <MenuSeparator /> : null}
          {moveTo.length > 0 ? <MenuNote>Move to…</MenuNote> : null}
          {moveTo.map((column) => (
            <MenuItem key={column.key} onSelect={() => onMove(task, column.key)}>{column.label}</MenuItem>
          ))}
        </Menu>
      </div>
      <div className="kcard__meta">
        {words ? <span className={cx("kcard__due", `kcard__due--${tone}`)}>{words}{parts?.time ? ` ${parts.time}` : ""}</span> : null}
        {project ? (
          <span className="kcard__project">
            <span className="dot" style={{ background: project.color }} aria-hidden="true" />{project.name}
          </span>
        ) : null}
        <StepsChip title={task.title} steps={task.steps} open={stepsOpen} onToggle={() => onToggleSteps(task.id)} />
        {showWho ? <Who bot={bot} /> : null}
      </div>
      {stepsOpen && task.steps.length > 0 ? (
        <SubSteps taskId={task.id} title={task.title} steps={task.steps} onSteps={onSteps} />
      ) : null}
    </div>
  );
}
