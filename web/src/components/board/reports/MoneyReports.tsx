import { useEffect, useState } from "react";
import { ErrorNotice } from "../../ErrorNotice";
import { ProjectBars } from "./ProjectBars";
import { TrendChart } from "./TrendChart";
import * as moneyApi from "../../../api/money";
import { describeError } from "../../../api/client";
import type { BoardProjectTotalOut, TrendMonthOut } from "../../../api/money";
import { Segmented } from "../../../ui/Segmented";

export interface MoneyReportsProps {
  rows: readonly BoardProjectTotalOut[]; // the shown month's by_project
  monthLabel: string; // "October 2026"
  projectId?: string;
}

type Span = "6" | "12";
const SPANS: ReadonlyArray<{ id: Span; label: string }> = [
  { id: "6", label: "Last 6 months" }, { id: "12", label: "Last 12 months" },
];

// The full reports (Task 15): the trend per currency over the last 6 months (what the side card showed) or 12, and
// the shown month by project. One lazy chunk with the trend chart, opened from Reports beside Export CSV.
export default function MoneyReports({ rows, monthLabel, projectId }: MoneyReportsProps) {
  const [span, setSpan] = useState<Span>("6");
  const [months, setMonths] = useState<readonly TrendMonthOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setMonths(null);
    moneyApi.getTrend(Number(span), projectId)
      .then((trend) => { if (current) { setMonths(trend.months); setError(null); } })
      .catch((err: unknown) => { if (current) setError(describeError(err)); });
    return () => { current = false; };
  }, [span, projectId]);
  return (
    <div className="reports">
      <section aria-label="Spent per month">
        <Segmented label="Months" options={SPANS} value={span} onChange={setSpan} />
        {error ? <ErrorNotice message={error} /> : months ? <TrendChart months={months} /> : <p className="board-loading">Loading&hellip;</p>}
      </section>
      <section aria-label="By project">
        <h3 className="reports__title">By project, {monthLabel}</h3>
        <ProjectBars rows={rows} />
      </section>
    </div>
  );
}
