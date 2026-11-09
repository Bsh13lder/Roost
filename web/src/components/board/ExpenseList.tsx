import { useRef, useState, type CSSProperties } from "react";
import { ExpenseEditRow, type ProjectChoice } from "./ExpenseEditRow";
import { FromLazyClawMark } from "./FromLazyClawMark";
import { MadeByChip } from "./MadeByChip";
import { WebContentChip } from "./WebContentChip";
import type { ExpenseActions } from "./useExpenseActions";
import { formatMoney } from "./money";
import { MoreIcon, PencilIcon } from "../icons";
import type { RangeExpenseOut } from "../../api/money";
import { Badge } from "../../ui/Badge";
import { IconButton } from "../../ui/IconButton";
import { Menu, MenuItem } from "../../ui/Menu";
import { cx } from "../../ui/cx";

export interface ExpenseRowProps {
  expense: RangeExpenseOut;
  currency: string; // the list's main one: an amount in another currency is marked apart
  showProject: boolean; // false on a project's own page, where every row is that project
  actions: ExpenseActions;
  projects: readonly ProjectChoice[]; // for the edit row's project; none keeps the project fixed
}

const LONG_PRESS_MS = 500; // a phone: press and hold a row to open its menu
const what = (expense: RangeExpenseOut) => `the ${expense.project} expense`;

// The star (P6): ☆ shows on hover or focus, ★ in warn always.
function Star({ expense, actions }: { expense: RangeExpenseOut; actions: ExpenseActions }) {
  return (
    <button type="button" className={cx("star", expense.is_favorite && "on")} aria-pressed={expense.is_favorite}
      aria-label={`Star ${what(expense)}`} onClick={() => actions.star(expense.id, !expense.is_favorite)}>
      {expense.is_favorite ? "★" : "☆"}
    </button>
  );
}

function Badges({ expense }: { expense: RangeExpenseOut }) {
  return (
    <>
      {expense.repeat ? <Badge>↻ {expense.repeat}</Badge> : null}
      {expense.kind === "income" ? <Badge tone="ok">money in</Badge> : null}
      {expense.status === "void" ? <Badge>void</Badge> : null}
    </>
  );
}

function RowMenu({ expense, actions, onEdit }: { expense: RangeExpenseOut; actions: ExpenseActions; onEdit: () => void }) {
  const [open, setOpen] = useState(false);
  const press = useRef<number | null>(null);
  return (
    <span className="xp__actions"
      onPointerDown={() => { press.current = window.setTimeout(() => setOpen(true), LONG_PRESS_MS); }}
      onPointerUp={() => { if (press.current !== null) window.clearTimeout(press.current); }}>
      <IconButton label={`Edit ${what(expense)}`} icon={<PencilIcon />} size="sm" onClick={onEdit} />
      <Menu label={`More for ${what(expense)}`} trigger={<MoreIcon />} open={open} onOpenChange={setOpen}>
        <MenuItem onSelect={onEdit}>Edit</MenuItem>
        {expense.status === "void"
          ? <MenuItem onSelect={() => actions.setVoid(expense, false)}>Restore</MenuItem>
          : <MenuItem onSelect={() => actions.setVoid(expense, true)}>Void</MenuItem>}
        <MenuItem onSelect={() => actions.remove(expense)}>Delete</MenuItem>
        {expense.tainted ? <MenuItem onSelect={() => actions.keep(expense.id)}>Keep</MenuItem> : null}
      </Menu>
    </span>
  );
}

// One expense, as the mockup's `.xp` row (Board redesign G9): star, project dot, note then vendor, the project's tag,
// the amount in its own column, and the actions on hover or focus. A void row is struck through; its amount is out of
// every total (the server's rule). Editing turns the row into its fields, in place.
export function ExpenseRow({ expense, currency, showProject, actions, projects }: ExpenseRowProps) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <ExpenseEditRow expense={expense} projects={showProject ? projects : []}
        onSave={(patch) => actions.edit(expense.id, patch)} onCancel={() => setEditing(false)} />
    );
  }
  const style = { "--pc": expense.project_color ?? "" } as CSSProperties;
  const classes = cx("xp", expense.status === "void" && "is-void", expense.kind === "income" && "xp--income",
    expense.currency !== currency && "xp--other");
  return (
    <li className={classes} style={style}>
      <Star expense={expense} actions={actions} />
      <span className="money-dot" aria-hidden="true" />
      <span className="xp__what">
        <span className="xp__n">{expense.description || expense.project}</span>
        <Badges expense={expense} />
        {expense.vendor ? <span className="xp__vendor">{expense.vendor}</span> : null}
        <MadeByChip botId={expense.created_by_bot} />
        <FromLazyClawMark from={expense.imported_from} />
        {expense.tainted ? <WebContentChip what={what(expense)} onKeep={() => actions.keep(expense.id)} /> : null}
      </span>
      {showProject ? <span className="xp__tag">{expense.project}</span> : <span />}
      <span className="xp__amt">{expense.kind === "income" ? "+" : ""}{formatMoney(expense.amount, expense.currency)}</span>
      <RowMenu expense={expense} actions={actions} onEdit={() => setEditing(true)} />
    </li>
  );
}

export interface ExpenseListProps extends Omit<ExpenseRowProps, "expense" | "projects"> {
  expenses: readonly RangeExpenseOut[];
}

// A plain list of rows: the task drawer's expenses. A task's expense keeps its project, so the edit row offers none.
export function ExpenseList({ expenses, currency, showProject, actions }: ExpenseListProps) {
  return (
    <ul className="xp-list" aria-label="Expenses">
      {expenses.map((expense) => (
        <ExpenseRow key={expense.id} expense={expense} currency={currency} showProject={showProject} actions={actions}
          projects={[]} />
      ))}
    </ul>
  );
}
