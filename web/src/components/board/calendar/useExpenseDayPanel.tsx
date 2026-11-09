import { useState, type ReactElement } from "react";
import { DayNoteMark } from "./DayNoteMark";
import { DayPopover } from "./DayPopover";
import { ExpenseDayList } from "./ExpenseDayList";
import type { DayNotes } from "./useDayNotes";
import { describeError } from "../../../api/client";
import { deleteExpense, type ExpenseLineOut, type MoneyRangeOut } from "../../../api/money";
import type { ExpenseOut } from "../../../api/types";
import { currencyList, formatMoneyShort } from "../money";
import { QuickAddBody } from "../QuickAddPopover";
import type { ExpenseActions } from "../useExpenseActions";
import { Button } from "../../../ui/Button";
import { Popover } from "../../../ui/Popover";
import { useToast } from "../../../ui/Toast";
import { dayText, type IsoDay } from "../../../ui/date/dates";

const PLACEHOLDER = "€12 lunch /Trip";

export interface ExpenseDayPanelInput {
  range: MoneyRangeOut;
  month: string;
  notes: DayNotes;
  actions: ExpenseActions;
  onChanged: () => void; // an expense was added or undone: load again
}

interface Active {
  day: IsoDay;
  mode: "day" | "add";
}

// The popover a money day opens (G12): its list, Day note and Add expense, or the expense line for that day. The
// month grid anchors it on a cell, the phone agenda on a day's header.
export function useExpenseDayPanel({ range, month, notes, actions, onChanged }: ExpenseDayPanelInput) {
  const toast = useToast();
  const [active, setActive] = useState<Active | null>(null);
  const close = () => setActive(null);
  const add = (day: IsoDay) => setActive({ day, mode: "add" });
  const inMonth = (day: IsoDay) => day.startsWith(month);
  const totalsOf = (day: IsoDay) => currencyList(range.days.find((entry) => entry.day === day)?.totals ?? {});

  const added = (made: ExpenseOut, line: ExpenseLineOut, day: IsoDay) => {
    const what = `${formatMoneyShort(line.amount ?? made.amount, line.currency)} ${line.note}`.trim();
    toast.show(`Added ${what} on ${dayText(day, { weekday: true })}`, {
      action: { label: "Undo", run: () => { deleteExpense(made.id).catch((err: unknown) => toast.show(describeError(err), { tone: "danger" })).finally(onChanged); } },
    });
    onChanged();
  };
  const panel = (day: IsoDay) => {
    const name = dayText(day, { weekday: true });
    if (active?.mode === "add") {
      return <QuickAddBody kind="expense" title={`Add expense on ${name}`} defaultDay={day} placeholder={PLACEHOLDER}
        onExpenseAdded={(made, line) => added(made, line, day)} onAdded={close} />;
    }
    return (
      <DayPopover kind="money" day={day} count={range.expenses.filter((e) => e.spent_at === day).length} totals={totalsOf(day)}
        notes={notes.byDay.get(day) ?? []} onAddNote={(text) => notes.add(day, text)} onDeleteNote={(note) => void notes.remove(note)}
        onClose={close} footer={<Button variant="ghost" size="sm" onClick={() => add(day)}>Add expense</Button>}>
        <ExpenseDayList range={range} day={day} actions={actions} />
      </DayPopover>
    );
  };
  const wrap = (day: IsoDay, anchor: ReactElement) => {
    const open = active?.day === day;
    const name = dayText(day, { weekday: true });
    return (
      <Popover anchor={anchor} open={open} onOpenChange={(next) => { if (!next) close(); }} align="start"
        label={open && active?.mode === "add" ? `Add expense on ${name}` : name}>
        {open ? panel(day) : null}
      </Popover>
    );
  };
  const noteMark = (day: IsoDay) => (
    <DayNoteMark day={day} count={inMonth(day) ? notes.byDay.get(day)?.length ?? 0 : 0} onOpen={() => setActive({ day, mode: "day" })} />
  );
  return { wrap, add, noteMark, totalsOf };
}
