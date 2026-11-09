import { useEffect, useId, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { SEARCH_PARAM } from "./sections";
import { ErrorNotice } from "../ErrorNotice";
import { SearchIcon } from "../icons";
import { TASK_SEARCH_DEBOUNCE_MS } from "../board/constants";
import { MAX_QUICK_LINE, TASK_PARAM } from "../tasks/constants";
import { blockerOf, chipsOf, taskInputOf } from "../tasks/quickChips";
import { useQuickLine } from "../tasks/useQuickLine";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import { useToast } from "../../ui/Toast";

export interface FindAddPillProps {
  projectId?: string; // the project chip picked: a new task joins it unless the line names another
}

export const PILL_LABEL = "Add or find anything";
const NO_SKIP: readonly tasksApi.QuickKindRich[] = [];

type Patch = (value: string | null) => void;

// The pill's words live in the address as ?q= (the tasks' search, the notes' filter), set after a pause in typing.
function useSearchWords(): [string, Patch] {
  const [params, setParams] = useSearchParams();
  const patch: Patch = (value) => setParams((current) => {
    const next = new URLSearchParams(current);
    if (value) next.set(SEARCH_PARAM, value); else next.delete(SEARCH_PARAM);
    return next;
  }, { replace: true });
  return [params.get(SEARCH_PARAM) ?? "", patch];
}

// The add: the server reads the line once more and exactly that reading is added, or it says what to fix.
function useAddLine(projectId: string | undefined, onDone: () => void) {
  const toast = useToast();
  const [, setParams] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const openTask = (id: string) => setParams((current) => {
    const next = new URLSearchParams(current);
    next.set(TASK_PARAM, id);
    return next;
  });
  const add = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const read = await tasksApi.parseQuickLine({ text, ...(projectId ? { project_id: projectId } : {}) });
      const blocker = blockerOf(read);
      if (blocker) { setProblem(blocker); return; }
      const made = await tasksApi.createTask(taskInputOf(read));
      toast.show(`Added “${made.title}”`, { action: { label: "Open", run: () => openTask(made.id) } });
      onDone();
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return { add, busy, problem, clear: () => setProblem(null) };
}

// "Add or find anything…" (app restructure, Workspace): what you type filters the tasks and the notes as you go,
// the server's reading shows as chips, and Enter adds it as a task. On a phone it sits in the bottom bar.
export function FindAddPill({ projectId }: FindAddPillProps) {
  const [words, setWords] = useSearchWords();
  const [text, setText] = useState(words);
  const chipsId = useId();
  const { line } = useQuickLine(text, projectId, NO_SKIP);
  const adder = useAddLine(projectId, () => { setText(""); setWords(null); });
  useEffect(() => {
    if (text.trim() === words) return undefined;
    const timer = window.setTimeout(() => setWords(text.trim() || null), TASK_SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text, words, setWords]);
  const submit = (event: FormEvent) => { event.preventDefault(); void adder.add(text); };
  const chips = line && text.trim() ? chipsOf(line) : [];
  return (
    <form className="find-pill" role="search" aria-label={PILL_LABEL} onSubmit={submit}>
      <div className="find-pill__box">
        <span className="find-pill__glyph" aria-hidden="true"><SearchIcon /></span>
        <input className="find-pill__input" role="combobox" aria-expanded={false} aria-label={PILL_LABEL}
          aria-describedby={chipsId} placeholder={`${PILL_LABEL}…`} value={text} maxLength={MAX_QUICK_LINE}
          autoComplete="off" disabled={adder.busy} onChange={(event) => { setText(event.target.value); adder.clear(); }} />
      </div>
      <div id={chipsId} className="find-pill__chips" aria-live="polite">
        {chips.map((chip, index) => (
          <span key={`${chip.kind}-${index}`} className={`quick-chip quick-chip--${chip.tone}`}>{chip.label}</span>
        ))}
      </div>
      {adder.problem ? <ErrorNotice message={adder.problem} /> : null}
    </form>
  );
}
