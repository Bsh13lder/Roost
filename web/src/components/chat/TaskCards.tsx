import { useState } from "react";
import { Link } from "react-router-dom";
import { completeTask, reopenTask, type TaskRowOut } from "../../api/tasks";
import { describeError } from "../../api/client";
import type { MessageOut } from "../../api/types";
import { parseTaskCards } from "../../lib/taskCards";
import { cx } from "../../ui/cx";
import { useChatShared } from "./chatContext";
import {
  TASK_CARDS_ADDED, TASK_CARDS_GONE, TASK_CARDS_LISTED, TASK_CARDS_MORE,
  TASK_CARDS_SHOWN, TASK_CARDS_SHOW_LESS, TASK_CARDS_SHOW_MORE,
} from "./constants";
import { TaskFacts, TaskTick, isFinished } from "./TaskCardParts";
import { useCardTasks } from "./useCardTasks";

function TaskCardRow({ task, onChanged }: { task: TaskRowOut; onChanged: () => void }) {
  const { openTask } = useChatShared();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const toggle = () => {
    setBusy(true);
    setProblem(null);
    (task.status === "done" ? reopenTask(task.id) : completeTask(task.id))
      .then(onChanged)
      .catch((err: unknown) => setProblem(describeError(err)))
      .finally(() => setBusy(false));
  };
  return (
    <li className={cx("task-card", isFinished(task) && "task-card--finished")}>
      <TaskTick task={task} busy={busy || task.status === "failed" || task.status === "cancelled"} onToggle={toggle} />
      <div className="task-card__main">
        {openTask ? (
          <button type="button" className="task-card__title" onClick={() => openTask(task.id)}>{task.title}</button>
        ) : <span className="task-card__title">{task.title}</span>}
        <TaskFacts task={task} />
        {problem ? <span className="task-card__problem" role="alert">{problem}</span> : null}
      </div>
    </li>
  );
}

// The first TASK_CARDS_SHOWN rows, and a toggle for the rest when there are more.
function TaskCardList({ tasks, onChanged }: { tasks: readonly TaskRowOut[]; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const hidden = tasks.length - TASK_CARDS_SHOWN;
  const shown = open || hidden <= 0 ? tasks : tasks.slice(0, TASK_CARDS_SHOWN);
  return (
    <>
      <ul className="task-cards__list">
        {shown.map((task) => <TaskCardRow key={task.id} task={task} onChanged={onChanged} />)}
      </ul>
      {hidden > 0 ? (
        <button type="button" className="task-cards__toggle" aria-expanded={open} onClick={() => setOpen((was) => !was)}>
          {open ? TASK_CARDS_SHOW_LESS : TASK_CARDS_SHOW_MORE.replace("{count}", String(hidden))}
        </button>
      ) : null}
    </>
  );
}

function heading(verb: string, count: number): string {
  if (verb === "added") return `${TASK_CARDS_ADDED} ${count === 1 ? "a task" : `${count} tasks`}`;
  return TASK_CARDS_LISTED;
}

// The tasks a bot added or listed in your chat (2026-10-26, owner: "when I ask task for it showed me beautiful"):
// one quiet card of task rows under its reply. Tick one to finish it, tap its title to open its drawer.
export function TaskCards({ message }: { message: MessageOut }) {
  const data = parseTaskCards(message.body);
  const { tasks, error, reload } = useCardTasks(data?.taskIds ?? []);
  if (!data) return null;
  const label = heading(data.verb, data.taskIds.length);
  return (
    <li className="message message--task-cards" data-message-id={message.id}>
      <section className="task-cards" aria-label={label}>
        <h4 className="task-cards__head">{label}</h4>
        {tasks === null && !error ? <p className="task-cards__quiet">Loading&hellip;</p> : null}
        {error ? <p className="task-cards__quiet" role="alert">{error}</p> : null}
        {tasks && tasks.length === 0 ? <p className="task-cards__quiet">{TASK_CARDS_GONE}</p> : null}
        {tasks && tasks.length > 0 ? <TaskCardList tasks={tasks} onChanged={reload} /> : null}
        {data.more > 0 ? (
          <Link className="task-cards__more" to="/board">{TASK_CARDS_MORE.replace("{count}", String(data.more))}</Link>
        ) : null}
      </section>
    </li>
  );
}
