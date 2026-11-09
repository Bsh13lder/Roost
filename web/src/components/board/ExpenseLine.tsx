import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { QuickBox } from "./QuickBox";
import { blockerOf, chipsOf, expenseInputOf, type ExpenseChip } from "./expenseChips";
import { accept, suggestProject, type SuggestOption } from "./expenseSuggest";
import { useExpenseLine } from "./useExpenseLine";
import { CloseIcon } from "../icons";
import { MAX_QUICK_LINE } from "../tasks/constants";
import { QuickHelp } from "../tasks/QuickHelp";
import { EXPENSE_TOKENS } from "../tasks/quickHelpTokens";
import { optionId, QuickSuggestList } from "../tasks/QuickSuggestList";
import { useProjects } from "../tasks/useProjects";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { ExpenseIn, ExpenseKind, ExpenseLineOut } from "../../api/money";
import type { ExpenseOut } from "../../api/types";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { dayText, type IsoDay } from "../../ui/date/dates";

// A task's drawer: the project and the task are fixed. The line never reads a /project (its words stay in the note),
// and the expense is filed under the task, or one of its steps, in the task's project (none when the task has none).
export interface FixedTask {
  projectId: string | null;
  taskId: string;
  stepId?: string;
  label: string; // the task's title, shown as "For <title>"
}

export interface ExpenseLineProps {
  projectId?: string; // a project's page: an expense with no /project goes to it
  fixed?: FixedTask;
  onAdded: (made: ExpenseOut, line: ExpenseLineOut) => void; // the expense just made, and the reading it came from
  defaultDay?: IsoDay; // the money calendar's day: the day of a line that names none ("On Wed 21 Oct" shows first)
  autoFocus?: boolean;
  placeholder?: string; // the empty line's hint
  submitLabel?: string; // the button, "Add" by default
}

const HINT = "Add an expense… try “€12 lunch /Trip yesterday vendor:Mercadona *”";

const removable = (chip: ExpenseChip): chip is ExpenseChip & { kind: ExpenseKind } => chip.kind !== "warning";
const NO_SKIP: readonly ExpenseKind[] = [];
const FIXED_SKIP: readonly ExpenseKind[] = ["project"];

// What the server is asked to read: a fixed task never reads a /project.
function readSkip(skip: readonly ExpenseKind[], fixed: FixedTask | undefined): readonly ExpenseKind[] {
  if (!fixed) return skip;
  return skip.includes("project") ? skip : skip.length ? [...skip, "project"] : FIXED_SKIP;
}

// What is added: exactly the reading, filed under the fixed task (and in its project) when there is one.
function addInput(read: ExpenseLineOut, projectId: string | undefined, fixed: FixedTask | undefined): ExpenseIn {
  if (!fixed) return expenseInputOf(read, projectId);
  const link = { task_id: fixed.taskId, ...(fixed.stepId ? { step_id: fixed.stepId } : {}) };
  return { ...expenseInputOf({ ...read, project: null }, projectId), ...link };
}

// The expense line (Task 7, in the Money tab's QuickBox): as you type, the server's reading shows as chips
// (amount, project, day, vendor, star, repeat), and Enter adds exactly that reading, or says what to fix.
// `/` suggests every project. A chip's × leaves its words in the note.
export function ExpenseLine({
  projectId: pageProject, fixed, onAdded, defaultDay, autoFocus = false, placeholder = HINT, submitLabel = "Add",
}: ExpenseLineProps) {
  const projectId = fixed ? fixed.projectId ?? undefined : pageProject;
  const [text, setText] = useState("");
  const [caret, setCaret] = useState(0);
  const [chosenSkip, setSkip] = useState<readonly ExpenseKind[]>(NO_SKIP);
  const skip = readSkip(chosenSkip, fixed);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [closed, setClosed] = useState(false);
  const [wantsProjects, setWantsProjects] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const nextCaret = useRef<number | null>(null);
  const { line, error } = useExpenseLine(text, projectId, skip, defaultDay);
  const chipsId = useId();
  const listId = useId();
  const projects = useProjects(wantsProjects);
  const names = useMemo(() => projects.map((project) => project.name), [projects]);
  const suggestion = useMemo(() => (closed || fixed ? null : suggestProject(text, caret, names)), [closed, fixed, text, caret, names]);

  useEffect(() => { if (autoFocus) input.current?.focus(); }, [autoFocus]);
  useLayoutEffect(() => {
    if (nextCaret.current === null) return;
    input.current?.setSelectionRange(nextCaret.current, nextCaret.current);
    nextCaret.current = null;
  }, [text]);

  const change = (next: string, at: number) => {
    setText(next);
    setCaret(at);
    setProblem(null);
    setClosed(false);
    setActive(0);
    if (next.includes("/") && !fixed) setWantsProjects(true);
    if (!next.trim()) setSkip(NO_SKIP);
  };
  const pick = (option: SuggestOption) => {
    if (!suggestion) return;
    const picked = accept(text, suggestion, option);
    nextCaret.current = picked.caret;
    change(picked.text, picked.caret);
    input.current?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!suggestion) return;
    const count = suggestion.options.length;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActive((now) => (now + (event.key === "ArrowDown" ? 1 : count - 1)) % count);
    } else if ((event.key === "Tab" && !event.shiftKey) || event.key === "Enter") {
      event.preventDefault();
      pick(suggestion.options[Math.min(active, count - 1)]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setClosed(true);
    }
  };
  const add = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      const read = await moneyApi.parseExpenseLine({
        text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}),
        ...(defaultDay ? { default_day: defaultDay } : {}),
      });
      const blocker = blockerOf(read);
      if (blocker) { setProblem(blocker); return; }
      const made = await moneyApi.createExpense(addInput(read, projectId, fixed));
      change("", 0);
      onAdded(made, read);
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const said = problem ?? (line ? blockerOf(line) : null);
  const chips = line ? chipsOf(line) : [];
  const dayBadge = defaultDay && !chips.some((chip) => chip.kind === "date") ? `On ${dayText(defaultDay, { weekday: true })}` : null;
  return (
    <form className="quick-add" onSubmit={(event) => { event.preventDefault(); void add(); }}>
      <QuickBox glyph="€" label="Add an expense" help={<QuickHelp tokens={EXPENSE_TOKENS} />} chips={
        <div id={chipsId} className="quick-add__reading" aria-live="polite">
          {fixed ? <span className="quick-chip quick-chip--read">For {fixed.label}</span> : null}
          {dayBadge ? <span className="quick-chip quick-chip--read">{dayBadge}</span> : null}
          {chips.map((chip, index) => (
            <span key={`${chip.kind}-${index}`} className={`quick-chip quick-chip--${chip.tone}`}>
              {chip.label}
              {removable(chip) ? (
                <button type="button" className="quick-chip__remove" aria-label={`Remove ${chip.label}`}
                  onClick={() => setSkip((kinds) => [...kinds, chip.kind])}><CloseIcon /></button>
              ) : null}
            </span>
          ))}
        </div>
      }>
        <div className="quick-add__row">
          <div className="quick-add__field">
            <Input ref={input} aria-label="New expense" aria-describedby={chipsId} placeholder={placeholder} value={text}
              controlSize="md" maxLength={MAX_QUICK_LINE} autoComplete="off" role="combobox" aria-autocomplete="list"
              aria-expanded={suggestion !== null} aria-controls={suggestion ? listId : undefined}
              aria-activedescendant={suggestion ? optionId(listId, Math.min(active, suggestion.options.length - 1)) : undefined}
              onChange={(event) => change(event.target.value, event.target.selectionStart ?? event.target.value.length)}
              onSelect={(event) => setCaret(event.currentTarget.selectionStart ?? text.length)} onKeyDown={onKeyDown} />
            {suggestion ? (
              <QuickSuggestList id={listId} options={suggestion.options} active={Math.min(active, suggestion.options.length - 1)}
                onPick={pick} onHover={setActive} />
            ) : null}
          </div>
          <Button type="submit" variant="primary" size="sm" disabled={busy || !text.trim()}>{submitLabel}</Button>
        </div>
      </QuickBox>
      {said ? <p className="quick-add__ask">{said}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
