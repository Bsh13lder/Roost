import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { ErrorNotice } from "../ErrorNotice";
import { QuickBox } from "../board/QuickBox";
import { CloseIcon } from "../icons";
import { MAX_QUICK_LINE } from "./constants";
import { blockerOf, chipsOf, taskInputOf, type QuickChip } from "./quickChips";
import { isCancelled, keepWords, stillTyped } from "./quickKept";
import { accept, suggest, type SuggestOption } from "./quickSuggest";
import { PasteConfirm } from "./PasteConfirm";
import { isPastedList, usePastedList } from "./usePastedList";
import { QuickHelp } from "./QuickHelp";
import { QuickPickers } from "./QuickPickers";
import { optionId, QuickSuggestList } from "./QuickSuggestList";
import { useProjects } from "./useProjects";
import { useTags } from "./useTags";
import { useQuickLine } from "./useQuickLine";
import * as tasksApi from "../../api/tasks";
import { describeError } from "../../api/client";
import type { QuickKindRich } from "../../api/tasks";
import type { TaskOut } from "../../api/types";
import { useLiveState } from "../../hooks/useLiveStore";
import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";

// What a Kanban column's "+" fills in (G6): used only where the line itself says nothing.
export interface QuickAddDefaults {
  priority?: TaskOut["priority"];
  category?: string;
  status?: "todo" | "in_progress";
}

export interface QuickAddProps {
  projectId?: string; // a project's page: a new task joins it unless the line names another
  onAdded: (made?: TaskOut) => void; // the task just made (not given after a pasted list)
  defaultDue?: string; // "YYYY-MM-DD": the due of a line that names no day (a column or a calendar day)
  prefill?: string; // the line starts as this, caret at the end ("/Casa Nueva ")
  defaults?: QuickAddDefaults; // priority, list or status a line that names none gets
  autoFocus?: boolean;
  placeholder?: string; // the empty line's hint (a calendar day shows an example)
  dayBadge?: string; // "Due Wed 21 Oct": the first chip while the line itself names no day (a calendar day's quick add)
}

const HINT = "Add a task… try “Call plumber friday 9am /Casa Nueva €200 !!”";

// A column's priority and list fill only what the line left empty.
function withDefaults(input: tasksApi.TaskIn, defaults: QuickAddDefaults | undefined): tasksApi.TaskIn {
  if (!defaults) return input;
  return {
    ...input,
    ...(defaults.priority && !input.priority ? { priority: defaults.priority } : {}),
    ...(defaults.category && !input.category ? { category: defaults.category } : {}),
  };
}

// Which chips can be removed with ×: all but the warnings, which only say something.
const removable = (chip: QuickChip): chip is QuickChip & { kind: QuickKindRich } => chip.kind !== "warning";

// The quick-add line (redesign P3, richer in Tasks & Money polish): as you type, the server's reading
// shows as chips (date, reminder, repeat, project, budget, priority, star, estimate, @bot) and the title it
// will add. #, @ and ! suggest names from the lists already loaded. Enter reads the line once more and adds
// exactly that reading, or says what to fix; a task is only handed to a bot once its chip is confirmed.
// A chip's × keeps its words in the title instead.
export function QuickAdd({ projectId, onAdded, defaultDue, prefill = "", defaults, autoFocus = false, placeholder = HINT, dayBadge }: QuickAddProps) {
  const [text, setText] = useState(prefill);
  const [caret, setCaret] = useState(prefill.length);
  const [skip, setSkip] = useState<readonly QuickKindRich[]>([]); // kinds dismissed with no words to keep
  const [kept, setKept] = useState<readonly string[]>([]); // words whose chips were cancelled: plain text now
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirmedBot, setConfirmedBot] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [closed, setClosed] = useState(false);
  const [wantsProjects, setWantsProjects] = useState(prefill.includes("/"));
  const [wantsTags, setWantsTags] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const nextCaret = useRef<number | null>(null);
  const { line, error } = useQuickLine(text, projectId, skip, kept, defaultDue);
  const pasted = usePastedList(projectId, onAdded);
  const chipsId = useId();
  const listId = useId();
  const projects = useProjects(wantsProjects);
  const tags = useTags(wantsTags);
  const bots = useLiveState().bots;
  const sources = useMemo(() => ({
    projects: projects.map((project) => project.name), tags, bots: Object.values(bots).map((bot) => bot.name),
  }), [projects, tags, bots]);
  const suggestion = useMemo(() => (closed ? null : suggest(text, caret, sources)), [closed, text, caret, sources]);

  useEffect(() => {
    if (!autoFocus) return;
    input.current?.focus();
    input.current?.setSelectionRange(prefill.length, prefill.length);
  }, [autoFocus, prefill.length]);

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
    if (next.includes("/")) setWantsProjects(true);
    if (next.includes("#")) setWantsTags(true);
    setKept((words) => stillTyped(words, next));
    if (!next.trim()) { setSkip([]); setKept([]); setConfirmedBot(null); }
  };
  const pick = (option: SuggestOption) => {
    if (!suggestion) return;
    const picked = accept(text, suggestion, option);
    nextCaret.current = picked.caret;
    change(picked.text, picked.caret);
    input.current?.focus();
  };
  const onPaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const clip = event.clipboardData.getData("text");
    if (!isPastedList(clip)) return; // one line: the input takes it as usual
    event.preventDefault();
    void pasted.read(clip);
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
      const read = await tasksApi.parseQuickLine({
        text, ...(projectId ? { project_id: projectId } : {}), ...(skip.length ? { skip: [...skip] } : {}),
        ...(kept.length ? { keep: [...kept] } : {}), ...(defaultDue ? { default_due: defaultDue } : {}),
      });
      const blocker = blockerOf(read, confirmedBot);
      if (blocker) { setProblem(blocker); return; }
      const made = await tasksApi.createTask(withDefaults(taskInputOf(read, confirmedBot), defaults));
      if (defaults?.status === "in_progress") await tasksApi.updateTask(made.id, { status: "in_progress" });
      change("", 0);
      onAdded(made);
    } catch (err) {
      setProblem(describeError(err));
    } finally {
      setBusy(false);
    }
  };
  const said = problem ?? (line ? blockerOf(line, confirmedBot) : null);
  const chips = line ? chipsOf(line, confirmedBot).filter((chip) => !isCancelled(chip, kept)) : [];
  const cancel = (chip: QuickChip & { kind: QuickKindRich }) => {
    if (chip.words?.length) setKept((words) => keepWords(words, chip.words ?? []));
    else setSkip((kinds) => [...kinds, chip.kind]);
  };
  return (
    <form className="quick-add" onSubmit={(event) => { event.preventDefault(); void add(); }}>
      <QuickBox glyph="+" label="Add a task" help={<QuickHelp />} chips={
        <>
          <QuickPickers text={text} matches={line?.matches} projects={sources.projects} tags={sources.tags}
            onText={(next) => { change(next, next.length); input.current?.focus(); }}
            onNeed={(list) => (list === "projects" ? setWantsProjects(true) : setWantsTags(true))} />
          <div id={chipsId} className="quick-add__reading" aria-live="polite">
            {line && line.title && line.title !== text.trim() ? <span className="quick-add__title">{line.title}</span> : null}
            {dayBadge && !chips.some((chip) => chip.kind === "date") ? <span className="quick-chip quick-chip--read">{dayBadge}</span> : null}
            {chips.map((chip, index) => (
              <span key={`${chip.kind}-${index}`} className={`quick-chip quick-chip--${chip.tone}`}>
                {chip.confirm ? (
                  <button type="button" className="quick-chip__action" onClick={() => setConfirmedBot(chip.confirm?.id ?? null)}>
                    {chip.label}
                  </button>
                ) : chip.label}
                {removable(chip) ? (
                  <button type="button" className="quick-chip__remove" aria-label={`Remove ${chip.label}`}
                    onClick={() => cancel(chip)}><CloseIcon /></button>
                ) : null}
              </span>
            ))}
          </div>
        </>
      }>
        <div className="quick-add__row">
          <div className="quick-add__field">
            <Input ref={input} aria-label="New task" aria-describedby={chipsId} placeholder={placeholder} value={text}
              controlSize="md" maxLength={MAX_QUICK_LINE} autoComplete="off" role="combobox" aria-autocomplete="list"
              aria-expanded={suggestion !== null} aria-controls={suggestion ? listId : undefined}
              aria-activedescendant={suggestion ? optionId(listId, Math.min(active, suggestion.options.length - 1)) : undefined}
              onChange={(event) => change(event.target.value, event.target.selectionStart ?? event.target.value.length)}
              onSelect={(event) => setCaret(event.currentTarget.selectionStart ?? text.length)} onKeyDown={onKeyDown}
              onPaste={onPaste} />
            {suggestion ? (
              <QuickSuggestList id={listId} options={suggestion.options} active={Math.min(active, suggestion.options.length - 1)}
                onPick={pick} onHover={setActive} />
            ) : null}
          </div>
          <Button type="submit" variant="primary" size="sm" disabled={busy || !text.trim()}>Add</Button>
        </div>
      </QuickBox>
      {pasted.list ? (
        <PasteConfirm list={pasted.list} busy={pasted.busy} onConfirm={() => void pasted.confirm()} onCancel={pasted.cancel} />
      ) : null}
      {pasted.error ? <ErrorNotice message={pasted.error} /> : null}
      {said ? <p className="quick-add__ask">{said}</p> : null}
      {error ? <ErrorNotice message={error} /> : null}
    </form>
  );
}
