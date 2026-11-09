import { formatMoney } from "../board/money";
import type { QuickKindRich, QuickLineRichOut, TaskIn } from "../../api/tasks";
import type { TaskOut } from "../../api/types";
import { dueParts, friendlyDue, pickerText, wallText } from "../../ui/date/dates";

// The quick add's chips (redesign P3, richer in Tasks & Money polish), drawn from the server's reading of
// the line. A chip the server could not use as typed (a project to ask about, a budget it refused) is shown
// as typed, to fix ("ask": Enter waits). A warning ("warn") says something and never blocks.
export interface QuickChip {
  kind: QuickKindRich | "warning";
  label: string;
  tone: "read" | "ask" | "warn";
  words?: string[]; // the typed words this chip came from; removing the chip keeps them as plain text
  confirm?: { id: string; name: string }; // the @bot chip: a button to confirm handing the task over
}

const MINUTES_PER_HOUR = 60;

/** "1h 30m", "45m", "2h". */
export function formatEstimate(minutes: number): string {
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  const rest = minutes % MINUTES_PER_HOUR;
  return [hours ? `${hours}h` : "", rest ? `${rest}m` : ""].filter(Boolean).join(" ");
}

function friendly(text: string): string {
  const parts = dueParts(text);
  return parts ? friendlyDue(parts) : text;
}

// The server's own words for the resolved date ("Wed 21 Oct 09:00", on the account's clock) when it sent them.
function dateChip(line: QuickLineRichOut): QuickChip[] {
  if (!line.due_date) return [];
  return [{ kind: "date", label: line.due_text ?? friendly(pickerText(line.due_date)), tone: "read" }];
}

function projectChip(line: QuickLineRichOut): QuickChip[] {
  if (line.project) return [{ kind: "project", label: `/${line.project.name}`, tone: "read" }];
  return line.project_words ? [{ kind: "project", label: line.project_words, tone: "ask" }] : [];
}

function budgetChip(line: QuickLineRichOut): QuickChip[] {
  const currency = line.budget_currency ?? line.project?.currency; // General's when the task is in no project
  if (line.budget && currency) {
    const money = formatMoney(line.budget, currency);
    return [{ kind: "budget", label: line.budget_math ? `${money} = ${line.budget_math}` : money, tone: "read" }];
  }
  return line.budget_words ? [{ kind: "budget", label: line.budget_words, tone: "ask" }] : [];
}

function priorityChip(priority: TaskOut["priority"] | null): QuickChip[] {
  return priority ? [{ kind: "priority", label: `!${priority}`, tone: "read" }] : [];
}

function reminderChip(line: QuickLineRichOut): QuickChip[] {
  if (line.reminder_at) {
    return [{ kind: "reminder", label: `Remind ${line.reminder_text ?? friendly(wallText(line.reminder_at))}`, tone: "read" }];
  }
  return line.reminder_words ? [{ kind: "reminder", label: line.reminder_words, tone: "warn" }] : [];
}

function repeatChip(line: QuickLineRichOut): QuickChip[] {
  if (line.recurring) return [{ kind: "repeat", label: line.repeat_text ?? line.recurring, tone: "read" }];
  return line.repeat_words ? [{ kind: "repeat", label: line.repeat_words, tone: "ask" }] : [];
}

function assigneeChip(line: QuickLineRichOut, confirmedId: string | null): QuickChip[] {
  const bot = line.assignee;
  if (bot) {
    return confirmedId === bot.id
      ? [{ kind: "assignee", label: `Handing to ${bot.name}`, tone: "read" }]
      : [{ kind: "assignee", label: `Assign to ${bot.name}`, tone: "read", confirm: bot }];
  }
  return line.assignee_words ? [{ kind: "assignee", label: line.assignee_words, tone: "ask" }] : [];
}

function tagChips(line: QuickLineRichOut): QuickChip[] {
  return (line.tags ?? []).map((tag): QuickChip => ({ kind: "tag", label: `#${tag}`, tone: "read" }));
}

function plainChips(line: QuickLineRichOut): QuickChip[] {
  return [
    ...(line.starred ? [{ kind: "star", label: "Starred", tone: "read" } as const] : []),
    ...(line.estimate_minutes ? [{ kind: "estimate", label: `~${formatEstimate(line.estimate_minutes)}`, tone: "read" } as const] : []),
  ];
}

function withWords(line: QuickLineRichOut, chips: QuickChip[]): QuickChip[] {
  return chips.map((chip) => {
    if (chip.kind === "warning") return chip;
    const words = chip.kind === "tag" ? [chip.label] : line.matches?.[chip.kind];
    return words?.length ? { ...chip, words } : chip;
  });
}

export function chipsOf(line: QuickLineRichOut, confirmedId: string | null = null): QuickChip[] {
  return withWords(line, [
    ...dateChip(line), ...reminderChip(line), ...repeatChip(line), ...projectChip(line), ...budgetChip(line),
    ...priorityChip(line.priority), ...tagChips(line), ...plainChips(line), ...assigneeChip(line, confirmedId),
    ...(line.warnings ?? []).map((warning): QuickChip => ({ kind: "warning", label: warning, tone: "warn" })),
  ]);
}

/** What a ready reading adds: exactly what the server read. A bot is handed the task only once confirmed. */
export function taskInputOf(line: QuickLineRichOut & { steps?: string[] }, confirmedId: string | null = null): TaskIn {
  return {
    title: line.title,
    ...(line.due_date ? { due_date: line.due_date } : {}),
    ...(line.priority ? { priority: line.priority } : {}),
    ...(line.project ? { project_id: line.project.id } : {}),
    ...(line.budget ? { allocated_budget: line.budget } : {}), // in no project it counts in General's currency
    ...(line.steps?.length ? { steps: line.steps } : {}),
    ...(line.tags?.length ? { tags: line.tags } : {}),
    ...(line.starred ? { starred: true } : {}),
    ...(line.estimate_minutes ? { estimate_minutes: line.estimate_minutes } : {}),
    ...(line.reminder_at ? { reminder_at: line.reminder_at } : {}),
    ...(line.recurring ? { recurring: line.recurring } : {}),
    ...(line.recurring && line.recur_until ? { recur_until: line.recur_until } : {}),
    ...(line.assignee && confirmedId === line.assignee.id ? { assign_bot_id: line.assignee.id, assign_confirmed: true } : {}),
  };
}

/** Why a reading can't be added yet, in the server's words (or the confirm the web itself waits for). */
export function blockerOf(line: QuickLineRichOut, confirmedId: string | null = null): string | null {
  if (!line.ready) {
    return line.project_question ?? line.budget_problem ?? line.repeat_problem ?? line.assignee_question
      ?? "Give the task a title.";
  }
  if (line.assignee && confirmedId !== line.assignee.id) return `Confirm handing this to ${line.assignee.name} first.`;
  return null;
}
