import { useState } from "react";
import { completeTask, failTask, updateTask, type TaskRowOut } from "../../api/tasks";
import { answerReminder, type ReminderAnswer } from "../../api/threads";
import { ReschedulePopover, type DuePick } from "../board/ReschedulePopover";
import { useChatShared } from "./chatContext";
import { REMINDER_DONE, REMINDER_FAILED, REMINDER_SKIPPED, TASK_GONE } from "./constants";
import { actionProblem, answerWords, movedWords, pickedDue, wasSkippedHere } from "./reminderActions";
import { REMINDER_FOOT, ReportFoot } from "./ReportFoot";
import { useCardTasks } from "./useCardTasks";

export interface ReminderChipsProps {
  threadId: string;
  messageId: string;
  taskId: string;
  answer?: string | null; // the answer the server kept on the Report (from any screen), drawn instead of the chips
  answerDue?: string | null;
  tainted: boolean;
}

interface Outcome { answer: ReminderAnswer; due: string | null; words: string }

// A finished task says so even when no answer was kept (it was finished somewhere else).
function settledWords(task: TaskRowOut | undefined): string | null {
  if (task?.status === "done") return REMINDER_DONE;
  return task?.status === "failed" ? REMINDER_FAILED : null;
}

function Chips({ task, onOutcome, onProblem }: {
  task: TaskRowOut; onOutcome: (outcome: Outcome) => Promise<void>; onProblem: (words: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const run = (action: () => Promise<unknown>, outcome: Outcome) => {
    setBusy(true);
    action().then(() => onOutcome(outcome)).catch((err: unknown) => onProblem(actionProblem(err))).finally(() => setBusy(false));
  };
  const reschedule = (pick: DuePick) => {
    const due = pickedDue(task, pick);
    run(() => updateTask(task.id, { due_date: due }), { answer: "rescheduled", due, words: movedWords(task, pick) });
  };
  const chip = (label: string, onClick: () => void) => (
    <button type="button" className="reminder-chip" disabled={busy} onClick={onClick}>{label}</button>
  );
  return (
    <div className="reminder-chips" role="group" aria-label="Reminder actions">
      {chip("Done", () => run(() => completeTask(task.id), { answer: "done", due: null, words: REMINDER_DONE }))}
      {chip("Failed", () => run(() => failTask(task.id), { answer: "failed", due: null, words: REMINDER_FAILED }))}
      <ReschedulePopover title={`Reschedule “${task.title}”`} current={null} onPick={reschedule}
        trigger={<button type="button" className="reminder-chip" disabled={busy}>Reschedule</button>} />
      {chip("Skip", () => run(() => Promise.resolve(), { answer: "skipped", due: null, words: REMINDER_SKIPPED }))}
    </div>
  );
}

// Under a task reminder's bubble (owner, 2026-10-26: "like Grok", and "Done failed reschedule Skip" kept): four
// small quiet chips, then one quiet line of what happened, and the "🔔 Reminder" footer that opens the task. The
// answer is kept on the Report on the server (`answerReminder`), so the web and the phone both show it after a
// reload; Skip changes nothing else.
export function ReminderChips({ threadId, messageId, taskId, answer = null, answerDue = null, tainted }: ReminderChipsProps) {
  const { openTask } = useChatShared();
  const { tasks, error } = useCardTasks([taskId]);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [saveProblem, setSaveProblem] = useState<string | null>(null);
  const task = tasks?.[0];
  const gone = tasks !== null && !task;
  const kept = answerWords(answer, answerDue) ?? (wasSkippedHere(messageId) ? REMINDER_SKIPPED : null);
  const said = outcome ?? kept ?? settledWords(task) ?? (gone ? TASK_GONE : null);
  // Done, Failed and Reschedule already changed the task, so their line shows at once. A Skip is only its answer:
  // it folds once the server kept it, and a refused save keeps the chips and says why.
  const keep = async ({ answer: picked, due, words }: Outcome) => {
    if (picked !== "skipped") setOutcome(words);
    try {
      await answerReminder(threadId, messageId, picked, due);
      setOutcome(words);
    } catch (err: unknown) {
      if (picked === "skipped") setProblem(actionProblem(err));
      else setSaveProblem(`Not saved for your other screens: ${actionProblem(err)}`);
    }
  };
  return (
    <>
      {said ? <p className="reminder-chips__said" role="status">{said}</p> : null}
      {task && !said ? (
        <Chips task={task} onOutcome={keep}
          onProblem={(words) => (words === TASK_GONE ? setOutcome(TASK_GONE) : setProblem(words))} />
      ) : null}
      {error ? <p className="reminder-chips__quiet" role="alert">{error}</p> : null}
      {problem && !said ? <p className="reminder-chips__quiet" role="alert">{problem}</p> : null}
      {saveProblem ? <p className="reminder-chips__quiet" role="alert">{saveProblem}</p> : null}
      <ReportFoot label={REMINDER_FOOT} tainted={tainted}>
        {task && openTask ? (
          <>
            <span aria-hidden="true">·</span>
            <button type="button" className="report__log" aria-label={`Open task ${task.title}`} onClick={() => openTask(task.id)}>
              Open task
            </button>
          </>
        ) : null}
      </ReportFoot>
    </>
  );
}
