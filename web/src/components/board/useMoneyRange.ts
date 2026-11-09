import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { rangeFor, type DayRange, type RangePreset } from "./dateRanges";
import type { MoneyView } from "./MoneyToolbar";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { MoneyRangeOut } from "../../api/money";
import { isIsoDay, todayIn, type IsoDay } from "../../ui/date/dates";

const PRESETS = new Set<string>(["today", "week", "month", "last", "custom"]);

export interface MoneyRange {
  view: MoneyView;
  preset: RangePreset | null;
  custom: DayRange | null;
  day: IsoDay | null;
  shown: MoneyRangeOut | null; // the range's rows and totals: the filter's, else the month's (null while loading)
  error: string | null;
  setView: (view: MoneyView) => void;
  setPreset: (preset: Exclude<RangePreset, "custom"> | null) => void;
  applyCustom: (range: DayRange) => void;
  setDay: (day: IsoDay | null) => void;
  clearRange: () => void;
  reload: () => void; // ask the server for the filter's range again
}

const validDay = (value: string | null): IsoDay | null => (value && isIsoDay(value) ? value : null);

// The Money tab's view, date filter and picked day, kept in the address (?mview=days&range=week, or
// range=custom&from=…&to=…, and &day=…) so a reload or a shared link lands in the same place. With a filter
// it asks GET /api/money/range for that span; with none it reuses the month's rows (G9's call), so the same
// range is never fetched twice. The summary cards stay on the month either way.
export function useMoneyRange(monthRange: MoneyRangeOut | null, version: number): MoneyRange {
  const [params, setParams] = useSearchParams();
  const range = params.get("range");
  const from = validDay(params.get("from"));
  const to = validDay(params.get("to"));
  const custom = useMemo<DayRange | null>(() => (from && to && from <= to ? { from, to } : null), [from, to]);
  const preset = (range && PRESETS.has(range) && (range !== "custom" || custom) ? range : null) as RangePreset | null;
  const day = validDay(params.get("day"));
  const mview = params.get("mview");
  const view: MoneyView = mview === "days" || mview === "cal" ? mview : "list";
  const span = useMemo<DayRange | null>(() => {
    if (!preset) return null;
    return preset === "custom" ? custom : rangeFor(preset, todayIn());
  }, [preset, custom]);
  const [fetched, setFetched] = useState<{ key: string; data: MoneyRangeOut } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);
  const key = span ? `${span.from}..${span.to}` : "";
  useEffect(() => {
    if (!span) return undefined;
    const ticket = ++latest.current;
    moneyApi.getRange(span.from, span.to, undefined)
      .then((data) => { if (ticket === latest.current) { setFetched({ key, data }); setError(null); } })
      .catch((err: unknown) => { if (ticket === latest.current) setError(describeError(err)); });
    return () => { latest.current += 1; };
  }, [span, key, version, tick]);

  const update = useCallback((changes: Record<string, string | null>) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [name, value] of Object.entries(changes)) {
        if (value === null) next.delete(name); else next.set(name, value);
      }
      return next;
    }, { replace: true });
  }, [setParams]);
  const clearRange = useCallback(() => update({ range: null, from: null, to: null, day: null }), [update]);
  const shown = span ? (fetched && fetched.key === key ? fetched.data : null) : monthRange;
  return {
    view, preset, custom, day, shown, error,
    setView: (next) => update({ mview: next === "list" ? null : next }),
    setPreset: (next) => update({ range: next, from: null, to: null, day: null }),
    applyCustom: (next) => update({ range: "custom", from: next.from, to: next.to, day: null }),
    setDay: (next) => update({ day: next }),
    clearRange, reload: () => setTick((now) => now + 1),
  };
}
