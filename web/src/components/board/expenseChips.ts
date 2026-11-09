import { formatMoney } from "./money";
import type { ExpenseIn, ExpenseKind, ExpenseLineOut } from "../../api/money";

// The expense line's chips (Task 7), drawn from the server's reading. A chip the server could not use as
// typed (a project to ask about, an amount it refused) is shown as typed, to fix ("ask": Enter waits).
// A warning says something and never blocks. Removing a chip leaves its words in the note.
export interface ExpenseChip {
  kind: ExpenseKind | "warning";
  label: string;
  tone: "read" | "ask" | "warn";
}

export const NEEDS_AMOUNT_TEXT = "Add an amount, like €12.";

function amountChip(line: ExpenseLineOut): ExpenseChip[] {
  if (line.amount !== null) {
    const money = formatMoney(line.amount, line.currency);
    const shown = line.amount_math ? `${money} = ${line.amount_math}` : money;
    return [{ kind: "amount", label: line.income ? `Money in ${shown}` : shown, tone: "read" }];
  }
  return line.amount_words ? [{ kind: "amount", label: line.amount_words, tone: "ask" }] : [];
}

function projectChip(line: ExpenseLineOut): ExpenseChip[] {
  if (line.project) return [{ kind: "project", label: `/${line.project.name}`, tone: "read" }];
  return line.project_words ? [{ kind: "project", label: line.project_words, tone: "ask" }] : [];
}

// The resolved day ("Tue 20 Oct") shows once a day was typed; a day that can't be logged is shown as typed.
function dayChip(line: ExpenseLineOut): ExpenseChip[] {
  if (line.day_problem) return [{ kind: "date", label: line.day_words ?? line.spent_text, tone: "ask" }];
  return line.day_words ? [{ kind: "date", label: line.spent_text, tone: "read" }] : [];
}

function repeatChip(line: ExpenseLineOut): ExpenseChip[] {
  if (line.cadence) return [{ kind: "repeat", label: `Repeats ${line.cadence}`, tone: "read" }];
  return line.repeat_words ? [{ kind: "repeat", label: line.repeat_words, tone: "ask" }] : [];
}

export function chipsOf(line: ExpenseLineOut): ExpenseChip[] {
  return [
    ...amountChip(line), ...projectChip(line), ...dayChip(line),
    ...(line.vendor ? [{ kind: "vendor", label: `at ${line.vendor}`, tone: "read" } as const] : []),
    ...(line.starred ? [{ kind: "star", label: "Starred", tone: "read" } as const] : []),
    ...repeatChip(line),
    ...line.warnings.map((warning): ExpenseChip => ({ kind: "warning", label: warning, tone: "warn" })),
  ];
}

/** Why a reading can't be added yet, in the server's words (or the one the web adds for a missing amount). */
export function blockerOf(line: ExpenseLineOut): string | null {
  if (line.ready) return null;
  return line.amount_problem ?? line.project_question ?? line.day_problem ?? line.repeat_problem
    ?? line.income_problem ?? line.text_problem ?? NEEDS_AMOUNT_TEXT;
}

/** What a ready reading adds: exactly what the server read. */
export function expenseInputOf(line: ExpenseLineOut, projectId?: string): ExpenseIn {
  return {
    amount: line.amount ?? "0",
    currency: line.currency,
    ...(line.project ? { project_id: line.project.id } : projectId ? { project_id: projectId } : {}),
    ...(line.note ? { note: line.note } : {}),
    spent_at: line.spent_at,
    ...(line.vendor ? { vendor: line.vendor } : {}),
    ...(line.starred ? { starred: true } : {}),
    ...(line.income ? { income: true } : {}),
    ...(line.cadence ? { cadence: line.cadence } : {}),
  };
}
