import { cadenceText } from "./projects";
import { formatMoney } from "../board/money";
import { Badge } from "../../ui/Badge";
import { dayText } from "../../ui/date/dates";
import type { RecurringOut } from "../../api/money";

// "↻ Home insurance €42.00 · monthly · next 5 Nov", one badge per rule (G13).
export function RepeatingStrip({ rules }: { rules: readonly RecurringOut[] }) {
  if (rules.length === 0) return null;
  return (
    <div className="p-repeats" role="group" aria-label="Repeating">
      <span className="eyebrow">Repeating</span>
      {rules.map((rule) => (
        <Badge key={rule.id}>
          ↻ {rule.note ?? "Charge"} {formatMoney(rule.amount, rule.currency)} · {rule.cadence} · next {dayText(rule.next_due)}
        </Badge>
      ))}
    </div>
  );
}
