import type { CSSProperties } from "react";
import { formatMoney } from "../money";
import type { BoardProjectTotalOut } from "../../../api/money";

export interface ProjectBarsProps {
  rows: readonly BoardProjectTotalOut[]; // the month's by_project, the server's order
}

// The month's spending by project, one group per currency and one scale per group: a bar is a project against
// the biggest of its own currency, so nothing is ever added across currencies.
export function ProjectBars({ rows }: ProjectBarsProps) {
  const spent = rows.filter((row) => Number(row.spent) > 0);
  const codes = [...new Set(spent.map((row) => row.currency))].sort();
  if (codes.length === 0) return <p className="chart__none">Nothing spent this month.</p>;
  return (
    <div className="pbars">
      {codes.map((code) => {
        const group = spent.filter((row) => row.currency === code);
        const top = Math.max(...group.map((row) => Number(row.spent)));
        return (
          <div key={code} role="group" aria-label={code} className="pbars__group">
            <h4 className="pbars__code">{code}</h4>
            <ul className="pbars__list">
              {group.map((row) => (
                <li key={row.project_id} className="pbars__row" style={{ "--pc": row.color } as CSSProperties}>
                  <span className="pbars__name"><span className="money-dot" aria-hidden="true" />{row.project}</span>
                  <span className="pbars__amt">{formatMoney(row.spent, row.currency)}</span>
                  <span className="pbars__bar" aria-hidden="true">
                    <span style={{ width: `${Math.max(2, Math.round((Number(row.spent) / top) * 100))}%` }} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
