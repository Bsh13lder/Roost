import type { DayTotalOut } from "../../../api/money";
import { formatMoney } from "../money";

export interface ExpenseDayCellProps {
  entry: DayTotalOut | undefined; // the server's totals for the day, if it has any
  currency: string; // the main currency: the first line
}

// What a money-calendar cell holds (G12): the day's total in the main currency, then each other currency on its own
// line in blue. Every figure is the server's; a void expense is already out of them.
export function ExpenseDayCell({ entry, currency }: ExpenseDayCellProps) {
  if (!entry) return null;
  const main = entry.totals[currency];
  const others = Object.entries(entry.totals).filter(([code]) => code !== currency);
  return (
    <>
      {main ? <span className="ccell__tot ccell__tot--main">{formatMoney(main, currency)}</span> : null}
      {others.map(([code, amount]) => <span key={code} className="ccell__tot usd">{formatMoney(amount, code)}</span>)}
    </>
  );
}
