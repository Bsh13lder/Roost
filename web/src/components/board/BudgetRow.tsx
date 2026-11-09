import type { CSSProperties, ReactNode } from "react";
import { formatAmount, unsigned } from "./money";
import { Meter, type MeterTone } from "../../ui/Meter";
import type { BudgetLineOut } from "../../api/types";

export interface BudgetRowData {
  id: string;
  name: string;
  color: string;
  currency: string;
  spent: string; // this month's, in the project's own currency
  month: BudgetLineOut;
  total: BudgetLineOut | null;
}

export interface BudgetRowProps {
  data: BudgetRowData;
  action?: ReactNode; // the pin toggle
}

const toneOf = (line: BudgetLineOut): MeterTone => line.tone ?? "ok";

// "Over by €200.20" (danger) or "€300 left this month", from the server's remaining.
function monthSub(data: BudgetRowData) {
  const remaining = data.month.remaining ?? "0";
  const over = remaining.startsWith("-");
  return over
    ? <span className="bud__sub bud__sub--danger">Over by {formatAmount(unsigned(remaining), data.currency)}</span>
    : <span className="bud__sub">{formatAmount(remaining, data.currency)} left this month</span>;
}

function totalSub(total: BudgetLineOut, currency: string) {
  const remaining = total.remaining ?? "0";
  if (remaining.startsWith("-")) {
    return <span className="bud__sub bud__sub--danger">Over by {formatAmount(unsigned(remaining), currency)}</span>;
  }
  return <span className="bud__sub">{formatAmount(remaining, currency)} left of {formatAmount(total.budget ?? "0", currency)} total</span>;
}

// One project's budget (Board redesign G8), on the side column and on a Pinned card. With a monthly limit
// its bar is the month's; with only a total budget, the total's; with neither, just the amount and "No limit".
// The tones and percents are the server's.
export function BudgetRow({ data, action }: BudgetRowProps) {
  const style = { "--pc": data.color } as CSSProperties;
  const monthly = data.month.budget !== null && data.month.used_percent !== null;
  const totalBar = !monthly && data.total !== null && data.total.budget !== null && data.total.used_percent !== null;
  return (
    <div className="bud" role="group" aria-label={data.name} style={style}>
      <div className="bud__head">
        <span className="money-dot" aria-hidden="true" />
        <span className="bud__name">{data.name}</span>
        <span className="bud__r">
          {monthly ? (
            <>
              <span>{formatAmount(data.spent, data.currency)}</span>
              <span className="bud__cap">/ {formatAmount(data.month.budget ?? "0", data.currency)}</span>
            </>
          ) : (
            <>
              <span>{formatAmount(data.spent, data.currency)}</span>
              {totalBar ? <span className="bud__cap">this month</span> : null}
            </>
          )}
        </span>
        {action}
      </div>
      {monthly ? (
        <>
          <Meter label={`${data.name} this month`} value={data.month.used_percent ?? 0} tone={toneOf(data.month)} />
          {monthSub(data)}
        </>
      ) : totalBar && data.total ? (
        <>
          <Meter label={`${data.name} total budget`} value={data.total.used_percent ?? 0} tone={toneOf(data.total)} />
          {totalSub(data.total, data.currency)}
        </>
      ) : <span className="bud__sub">No limit</span>}
    </div>
  );
}
