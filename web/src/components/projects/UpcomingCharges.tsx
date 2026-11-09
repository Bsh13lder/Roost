import { formatMoney } from "../board/money";
import { dayText } from "../../ui/date/dates";
import type { UpcomingChargeOut } from "../../api/money";

// "Coming up": the next 31 days' repeating charges, soonest first, as the server lists them (G13).
export function UpcomingCharges({ charges }: { charges: readonly UpcomingChargeOut[] }) {
  return (
    <section className="money-card side-card" aria-label="Coming up">
      <h2 className="side-card__title">Coming up</h2>
      {charges.length === 0 ? <p className="side-card__empty">Nothing in the next 31 days.</p> : (
        <ul className="charge-list">
          {charges.map((charge) => (
            <li key={`${charge.recurring_id}-${charge.day}`} className="charge">
              <span>{charge.note ?? "Charge"} <span className="faint">· {dayText(charge.day)}</span></span>
              <span className="num">{formatMoney(charge.amount, charge.currency)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
