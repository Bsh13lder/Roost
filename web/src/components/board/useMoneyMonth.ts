import { useCallback, useEffect, useRef, useState } from "react";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { MoneyRangeOut, MoneySummaryBoardOut } from "../../api/money";

export interface MonthData {
  month: string;
  summary: MoneySummaryBoardOut;
  range: MoneyRangeOut; // the month's days and rows (a project page: that project's only)
}

const DAYS_IN = (year: number, month: number) => new Date(Date.UTC(year, month, 0)).getUTCDate();

/** The first and last day of a month on the account's calendar ("2026-10" → 2026-10-01, 2026-10-31). */
export function monthSpan(month: string): { first: string; last: string } {
  const [year, number] = month.split("-").map(Number);
  return { first: `${month}-01`, last: `${month}-${String(DAYS_IN(year, number)).padStart(2, "0")}` };
}

// One month's summary (on the account's calendar) and its days of expenses (GET /api/money/summary and /range). Only the newest
// request may paint (fast month clicks), and a reload follows every money_changed frame (`version`).
// `projectId` narrows the rows to one project (its page).
export function useMoneyMonth(month: string, version: number, projectId?: string) {
  const [data, setData] = useState<MonthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const load = useCallback(() => {
    const ticket = ++latest.current;
    const { first, last } = monthSpan(month);
    Promise.all([moneyApi.getSummary(month), moneyApi.getRange(first, last, projectId)])
      .then(([summary, range]) => {
        if (ticket === latest.current) { setData({ month, summary, range }); setError(null); }
      })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
  }, [month, projectId]);
  useEffect(() => load(), [load, version]);
  return { data: data && data.month === month ? data : null, error, report: setError, load };
}
