import { useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { WebContentChip } from "../board/WebContentChip";
import { RETIRED_BOT, momentText } from "./authors";
import { useLiveState } from "../../hooks/useLiveStore";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { TaskOut } from "../../api/types";

const ENDED: Partial<Record<TaskOut["status"], string>> = { done: "Done", failed: "Failed", cancelled: "Cancelled" };

// Who made it. A task with no maker was made by the user, or by a bot since retired (the store
// cannot tell them apart), so the drawer says both.
function makerText(botId: string | null, names: Readonly<Record<string, { name: string }>>): string {
  if (!botId) return "Made by you, or by a bot since retired";
  return `Made by ${names[botId]?.name ?? RETIRED_BOT.toLowerCase()}`;
}

// The drawer's Activity (redesign P3): who made the task, when it was made, last changed and finished,
// and the "from web content" mark with Keep. Roost keeps no history of changes beyond these.
export function TaskActivity({ task, onChanged }: { task: TaskOut; onChanged: () => void }) {
  const { bots } = useLiveState();
  const [error, setError] = useState<string | null>(null);
  const ended = ENDED[task.status];
  const keep = () => {
    setError(null);
    tasksApi.keepTask(task.id).then(onChanged).catch((err: unknown) => setError(describeError(err)));
  };
  return (
    <section className="task-drawer__section" aria-label="Activity">
      <h3 className="task-drawer__heading">Activity</h3>
      <ul className="task-activity">
        <li>{makerText(task.created_by_bot, bots)}, {momentText(task.created_at)}</li>
        <li>Last changed {momentText(task.updated_at)}</li>
        {ended && task.completed_at ? <li>{ended} {momentText(task.completed_at)}</li> : null}
      </ul>
      {task.tainted ? (
        <div className="task-activity__web">
          <WebContentChip what={task.title} onKeep={keep} />
        </div>
      ) : null}
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
