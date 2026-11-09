import type { ReactNode } from "react";
import { currencyList, formatAmount, formatMoney, monthShort, signedPercent } from "./money";
import { dayText } from "../../ui/date/dates";
import type { LimitItemOut, MoneySummaryBoardOut } from "../../api/money";

export interface MoneySummaryCardsProps {
  summary: MoneySummaryBoardOut;
  showToday?: boolean; // this month on screen: the Spent card's sub-line says what today added
}

function Kpi({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="money-card kpi" role="group" aria-label={name}>
      <span className="eyebrow">{name}</span>
      {children}
    </div>
  );
}

// The month against the last one, as the server worked it out: nothing when there is no earlier month.
function Change({ summary }: { summary: MoneySummaryBoardOut }) {
  if (summary.change_percent === null || summary.previous === null) return null;
  const direction = summary.change_percent > 0 ? "up" : summary.change_percent < 0 ? "down" : "flat";
  return (
    <span className={`kpi__change kpi__change--${direction}`}>
      {signedPercent(summary.change_percent)} vs {monthShort(summary.previous.month)}
    </span>
  );
}

// "Today: €84.20 · US$12", each currency alone, zero in the main one when nothing was spent today.
function TodayLine({ summary }: { summary: MoneySummaryBoardOut }) {
  return (
    <span className="kpi__s kpi__today">
      Today: <b className="num">{currencyList(summary.today.totals, formatMoney("0", summary.currency))}</b>
    </span>
  );
}

function SpentCard({ summary, showToday }: { summary: MoneySummaryBoardOut; showToday: boolean }) {
  const others = Object.entries(summary.other_currencies);
  return (
    <Kpi name="Spent this month">
      <span className="kpi__v">{formatMoney(summary.total, summary.currency)}</span>
      {showToday ? <TodayLine summary={summary} /> : null}
      <span className="kpi__s">
        {others.map(([code, amount]) => (
          <span key={code} className="kpi__apart">+ {formatMoney(amount, code)} apart</span>
        ))}
        <Change summary={summary} />
      </span>
    </Kpi>
  );
}

function limitText(item: LimitItemOut): string {
  const amount = formatAmount(item.amount, item.currency);
  return item.over ? `${item.project} over by ${amount}` : `${item.project} ${amount} left`;
}

function LimitsCard({ summary }: { summary: MoneySummaryBoardOut }) {
  const { over_count: over, items } = summary.limits;
  const headline = over > 0
    ? <span className="kpi__v kpi__v--danger">{over} over</span>
    : items.length > 0
      ? <span className="kpi__v kpi__v--ok">All on track</span>
      : <span className="kpi__v kpi__v--faint">No limits set</span>;
  return (
    <Kpi name="Monthly limits">
      {headline}
      {items.length > 0 ? <span className="kpi__s">{items.slice(0, 2).map(limitText).join(" · ")}</span> : null}
    </Kpi>
  );
}

function TopCard({ summary }: { summary: MoneySummaryBoardOut }) {
  const top = summary.top_project;
  return (
    <Kpi name="Top project">
      {top ? (
        <>
          <span className="kpi__v kpi__v--project" style={{ "--pc": top.color } as React.CSSProperties}>
            <span className="money-dot money-dot--lg" aria-hidden="true" />
            <span>{top.project}</span>
          </span>
          <span className="kpi__s">{formatAmount(top.spent, top.currency)} · {top.share_percent}% of the month</span>
        </>
      ) : (
        <>
          <span className="kpi__v kpi__v--faint">None yet</span>
          <span className="kpi__s">Nothing spent in {summary.currency} this month</span>
        </>
      )}
    </Kpi>
  );
}

function ComingCard({ summary }: { summary: MoneySummaryBoardOut }) {
  const { count, totals, next } = summary.coming_up;
  const main = totals[summary.currency];
  const others = Object.fromEntries(Object.entries(totals).filter(([code]) => code !== summary.currency));
  const otherText = currencyList(others);
  return (
    <Kpi name={`Coming up · ${summary.coming_up.days} days`}>
      <span className="kpi__v">
        {formatMoney(main ?? "0", summary.currency)}
        {otherText ? <small className="kpi__more"> + {otherText}</small> : null}
      </span>
      <span className="kpi__s">
        {count === 0 ? "No repeating charges"
          : `${count} repeating ${count === 1 ? "charge" : "charges"}${next ? ` · next ${next.note ?? "charge"}, ${dayText(next.day)}` : ""}`}
      </span>
    </Kpi>
  );
}

// The four cards over the Money tab (Board redesign G8). Every figure is the server's; two currencies are
// never added: the main one is the number, the others sit beside it.
export function MoneySummaryCards({ summary, showToday = false }: MoneySummaryCardsProps) {
  return (
    <div className="money-cards">
      <SpentCard summary={summary} showToday={showToday} />
      <LimitsCard summary={summary} />
      <TopCard summary={summary} />
      <ComingCard summary={summary} />
    </div>
  );
}
