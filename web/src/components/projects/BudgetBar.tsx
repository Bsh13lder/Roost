import { formatMoney } from "../board/money";
import { Meter } from "../../ui/Meter";
import type { BudgetLineOut } from "../../api/types";

export interface BudgetBarProps {
  label: string; // "Total budget" or "This month": the meter's name
  line: BudgetLineOut;
  currency: string; // the project's own
}

// "€180.00 left of €300.00", "Over by €45.00", or with no limit "€12.50 spent, no limit".
// The server sends every number (H8); this only formats them.
export function budgetText(line: BudgetLineOut, currency: string): string {
  const money = (amount: string) => formatMoney(amount, currency);
  if (line.budget === null || line.remaining === null) return `${money(line.spent)} spent, no limit`;
  return line.remaining.startsWith("-")
    ? `Over by ${money(line.remaining.slice(1))}`
    : `${money(line.remaining)} left of ${money(line.budget)}`;
}

// One budget as a bar (H8, H14): green below 80 %, amber from 80 %, red from 100 %, the tone
// being the server's. Over 100 % the bar is full; the text says by how much.
export function BudgetBar({ label, line, currency }: BudgetBarProps) {
  const text = budgetText(line, currency);
  if (line.budget === null || line.used_percent === null) {
    return (
      <p className="budget-bar budget-bar--none">
        <span className="budget-bar__label">{label}</span>
        <span className="budget-bar__text">{text}</span>
      </p>
    );
  }
  return (
    <div className="budget-bar">
      <div className="budget-bar__head">
        <span className="budget-bar__label">{label}</span>
        <span className={`budget-bar__text${line.tone === "over" ? " budget-bar__text--over" : ""}`}>{text}</span>
      </div>
      <Meter label={label} value={line.used_percent} tone={line.tone ?? "ok"} valueText={text} />
    </div>
  );
}
