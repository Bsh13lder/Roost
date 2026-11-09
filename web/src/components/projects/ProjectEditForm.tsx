import { useId, useState } from "react";
import { ErrorNotice } from "../ErrorNotice";
import {
  CURRENCY_HELP, CURRENCY_LENGTH, DEFAULT_CURRENCY, DEFAULT_PROJECT_COLOR, MAX_PROJECT_NAME, PROJECT_COLORS, readCurrency,
} from "./projects";
import { AMOUNT_HELP, MAX_AMOUNT_TEXT, readAmount } from "../board/money";
import { useLiveState } from "../../hooks/useLiveStore";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";
import { DatePicker } from "../../ui/date/DatePicker";
import { resolveDay } from "../../ui/date/resolve";
import * as projectsApi from "../../api/projects";
import { describeError } from "../../api/client";
import type { ProjectOut } from "../../api/types";

interface Fields {
  name: string;
  currency: string;
  budget: string; // the total budget, top-ups included; "" is none (or, on a saved project, clears it, H5)
  monthly: string;
  color: string;
  start: string;
  due: string;
  lead: string; // "" for no lead bot
}
type Setter = (key: keyof Fields, value: string) => void;

// The Select's word for "no lead bot" (Radix keeps "" for "nothing chosen"); a bot id is a UUID.
const NO_LEAD = "none";

interface Read {
  currency: string;
  budget: string | null;
  monthly: string | null;
}

function fieldsOf(project: ProjectOut | undefined): Fields {
  return {
    name: project?.name ?? "", currency: project?.currency ?? DEFAULT_CURRENCY, budget: project?.total.budget ?? "",
    monthly: project?.month.budget ?? "", color: project?.color ?? DEFAULT_PROJECT_COLOR,
    start: project?.start_date ?? "", due: project?.due_date ?? "", lead: project?.lead_bot_id ?? "",
  };
}

// The fields as the gateway takes them, or the sentence that says what to fix. A total budget left as
// it was when the form opened keeps the server's string unread: it can be "0.00" once every top-up is
// undone, which readAmount refuses.
function readFields(fields: Fields, openedBudget: string): Read | string {
  const currency = readCurrency(fields.currency);
  if (currency === null) return CURRENCY_HELP;
  const budget = fields.budget === openedBudget ? openedBudget || null : readAmount(fields.budget);
  const monthly = readAmount(fields.monthly);
  if (budget === undefined || monthly === undefined) return AMOUNT_HELP;
  return { currency, budget, monthly };
}

function draftFor(fields: Fields, read: Read): projectsApi.ProjectIn {
  return {
    name: fields.name.trim(), currency: read.currency, budget: read.budget, monthly_budget: read.monthly,
    color: fields.color, start_date: fields.start || null, due_date: fields.due || null, lead_bot_id: fields.lead || null,
  };
}

// Only what changed is sent. The total budget is not part of it: PATCH never takes it.
function patchFor(project: ProjectOut, fields: Fields, read: Read): projectsApi.ProjectPatchIn {
  const next: projectsApi.ProjectPatchIn = {
    name: fields.name.trim(), color: fields.color, start_date: fields.start || null, due_date: fields.due || null,
    monthly_budget: read.monthly, lead_bot_id: fields.lead || null, currency: read.currency,
  };
  const before: projectsApi.ProjectPatchIn = {
    name: project.name, color: project.color, start_date: project.start_date, due_date: project.due_date,
    monthly_budget: project.month.budget, lead_bot_id: project.lead_bot_id, currency: project.currency,
  };
  const changed = Object.entries(next).filter(([key, value]) => before[key as keyof projectsApi.ProjectPatchIn] !== value);
  return Object.fromEntries(changed) as projectsApi.ProjectPatchIn;
}

// Save on a saved project: what changed goes through updateProject, then the total budget through
// setProjectBudget, only when the user edited that field. It is compared with what the field held when
// the form opened, never with the project's latest total: a top-up added meanwhile (say, in the Money
// tab below) must not be undone by a Save that never touched the budget. "1000" typed over the
// opened "1000.00" is no change either.
function editRequest(project: ProjectOut, fields: Fields, read: Read, openedBudget: string): () => Promise<unknown> {
  const patch = patchFor(project, fields, read);
  const budgetChanged = fields.budget !== openedBudget && read.budget !== (openedBudget || null);
  return async () => {
    if (Object.keys(patch).length > 0) await projectsApi.updateProject(project.id, patch);
    if (budgetChanged) await projectsApi.setProjectBudget(project.id, read.budget);
  };
}

// The two dates as days: a picked day as it is, typed words read by the gateway first.
async function withDays(fields: Fields): Promise<Fields> {
  const [start, due] = await Promise.all([resolveDay(fields.start), resolveDay(fields.due)]);
  return { ...fields, start: start ?? "", due: due ?? "" };
}

// What Save sends, or the sentence that says why it can't yet.
function requestFor(project: ProjectOut | undefined, fields: Fields, openedBudget: string): (() => Promise<unknown>) | string {
  const read = readFields(fields, openedBudget);
  if (typeof read === "string") return read;
  return project ? editRequest(project, fields, read, openedBudget) : () => projectsApi.createProject(draftFor(fields, read));
}

function NameFields({ fields, set }: { fields: Fields; set: Setter }) {
  return (
    <>
      <label className="field project-edit__name"><span className="field__label">Name</span>
        <input className="input" value={fields.name} maxLength={MAX_PROJECT_NAME} onChange={(e) => set("name", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Currency</span>
        <input className="input" value={fields.currency} maxLength={CURRENCY_LENGTH} autoCapitalize="characters"
          onChange={(e) => set("currency", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Total budget</span>
        <input className="input" inputMode="decimal" placeholder="none" value={fields.budget} maxLength={MAX_AMOUNT_TEXT}
          onChange={(e) => set("budget", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Monthly limit</span>
        <input className="input" inputMode="decimal" placeholder="none" value={fields.monthly} maxLength={MAX_AMOUNT_TEXT}
          onChange={(e) => set("monthly", e.target.value)} />
      </label>
    </>
  );
}

function ColorPicker({ value, onChange }: { value: string; onChange: (color: string) => void }) {
  const group = useId();
  return (
    <fieldset className="field project-edit__colors">
      <legend className="field__label">Color</legend>
      <div className="project-swatches">
        {PROJECT_COLORS.map(([color, label]) => (
          <label key={color} className="project-swatch" style={{ background: color }} title={label}>
            <input type="radio" name={`${group}-color`} className="sr-only" aria-label={label}
              checked={value === color} onChange={() => onChange(color)} />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// The dates and the lead bot (H15: one of the user's own bots, which the gateway checks).
function WhenFields({ fields, set }: { fields: Fields; set: Setter }) {
  const live = useLiveState();
  const bots = [...Object.values(live.bots)].sort((a, b) => a.name.localeCompare(b.name));
  const leads: SelectOption[] = [{ value: NO_LEAD, label: "No lead bot" }, ...bots.map((bot) => ({ value: bot.id, label: bot.name }))];
  return (
    <>
      <Field label="Starts">
        <DatePicker value={fields.start} placeholder="a day, or empty" onChange={(day) => set("start", day)} />
      </Field>
      <Field label="Due">
        <DatePicker value={fields.due} placeholder="a day, or empty" onChange={(day) => set("due", day)} />
      </Field>
      <Field label="Lead bot" className="project-edit__lead">
        <Select value={fields.lead || NO_LEAD} options={leads}
          onChange={(lead) => set("lead", lead === NO_LEAD ? "" : lead)} />
      </Field>
    </>
  );
}

export interface ProjectEditFormProps {
  project?: ProjectOut; // none: a new project
  onDone: (made?: ProjectOut) => void; // saved (a new project comes with it), or cancelled
}

// Make a project, or change one (P6): its name, currency, budgets, color, dates and lead bot.
export function ProjectEditForm({ project, onDone }: ProjectEditFormProps) {
  const [opened] = useState<Fields>(() => fieldsOf(project)); // what the form showed when it opened
  const [fields, setFields] = useState<Fields>(opened);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set: Setter = (key, value) => setFields((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const request = requestFor(project, await withDays(fields), opened.budget);
      if (typeof request === "string") {
        setError(request);
        setBusy(false);
        return;
      }
      const saved = await request();
      onDone(project ? undefined : (saved as ProjectOut));
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };

  return (
    <form className="project-edit" aria-label={project ? `Edit ${project.name}` : "New project"}
      onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <NameFields fields={fields} set={set} />
      <ColorPicker value={fields.color} onChange={(color) => set("color", color)} />
      <WhenFields fields={fields} set={set} />
      {error ? <ErrorNotice message={error} /> : null}
      <div className="project-edit__actions">
        <button type="submit" className="btn btn--primary btn--small" disabled={busy || !fields.name.trim()}>
          {project ? "Save" : "Create project"}
        </button>
        <button type="button" className="btn btn--quiet btn--small" onClick={() => onDone()}>Cancel</button>
      </div>
    </form>
  );
}
