import { formatMoney } from "./money";

export interface RangeSummaryProps {
  count: number;
  totals: Readonly<Record<string, string>>; // per currency, the server's
  currency: string; // shown as zero when nothing was spent
  label: string; // "this week", "12 Oct–18 Oct", or "" for the month
  day?: string | null; // the picked day, "Sun 18 Oct"
}

// "12 expenses · €340.20 · US$12.00 this week; other currencies apart": the server's count and totals for the
// range, or for the picked day. Each currency stands alone.
export function RangeSummary({ count, totals, currency, label, day }: RangeSummaryProps) {
  const money = Object.entries(totals).map(([code, amount]) => formatMoney(amount, code));
  const figures = [`${count} ${count === 1 ? "expense" : "expenses"}`, ...(money.length ? money : [formatMoney("0", currency)])];
  const scope = [label, day].filter(Boolean).join(" · ");
  return (
    <p className="rsum">
      <b>{figures.join(" · ")}</b>{" "}
      <span className="rsum__scope">{scope ? `${scope}; ` : ""}other currencies apart</span>
    </p>
  );
}
