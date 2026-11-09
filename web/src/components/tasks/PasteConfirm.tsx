import type { PastedListOut } from "../../api/tasks";
import { Button } from "../../ui/Button";

export interface PasteConfirmProps {
  list: PastedListOut;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const noun = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

// "Add N tasks?" for a pasted list: the titles the server read (with how many steps each holds), then yes or no.
export function PasteConfirm({ list, busy, onConfirm, onCancel }: PasteConfirmProps) {
  return (
    <div className="quick-paste" role="group" aria-label="Pasted tasks">
      <p className="quick-paste__ask">{`Add ${noun(list.count, "task")}?`}</p>
      <ul className="quick-paste__list">
        {list.tasks.map((task, index) => (
          <li key={`${index}-${task.title}`} className="quick-paste__item">
            <span>{task.title}</span>
            {task.steps.length ? <span className="quick-paste__steps">{noun(task.steps.length, "step")}</span> : null}
          </li>
        ))}
      </ul>
      {list.problem ? <p className="quick-add__ask">{list.problem}</p> : null}
      <div className="quick-paste__actions">
        <Button variant="primary" disabled={busy || !list.ready || list.count === 0} onClick={onConfirm}>
          {`Add ${noun(list.count, "task")}`}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
