import { monthLabel } from "./money";

// A past month: the way back to this one, and how to log something on a past day (type it in the line).
export function PastMonth({ month, thisMonth, onBack }: { month: string; thisMonth: string; onBack: () => void }) {
  return (
    <div className="money-board__past">
      <button type="button" className="btn btn--quiet btn--small" onClick={onBack}>Back to {monthLabel(thisMonth)}</button>
      <p className="board-empty">Viewing {monthLabel(month)}. Type a day in the line, like ‘yesterday’ or ‘3/10’.</p>
    </div>
  );
}
