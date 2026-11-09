import type { ReactNode } from "react";
import { monthToGoText } from "./projects";
import { formatMoney, monthLabel, unsigned } from "../board/money";
import { Meter, type MeterTone } from "../../ui/Meter";
import type { ProjectDetailBoardOut } from "../../api/projects";
import type { BudgetLineOut } from "../../api/types";

interface StatProps {
  eyebrow: string;
  value: ReactNode;
  small?: string;
  danger?: boolean;
  meter?: { value: number; tone: MeterTone; label: string } | null;
  sub: ReactNode;
}

function Stat({ eyebrow, value, small, danger = false, meter = null, sub }: StatProps) {
  return (
    <div className="p-stat">
      <span className="eyebrow">{eyebrow}</span>
      <div className="p-stat__v">
        <span className={danger ? "danger" : undefined}>{value}</span>
        {small ? <> <small>{small}</small></> : null}
      </div>
      {meter ? <Meter label={meter.label} value={meter.value} tone={meter.tone} /> : null}
      <div className="p-stat__s">{sub}</div>
    </div>
  );
}

// The words and meter of one budget, all from the server's line: "€300.00 left of €1,500.00", or in danger "€200.20 over …".
function budgetStat(line: BudgetLineOut, currency: string, label: string) {
  const money = (amount: string) => formatMoney(amount, currency);
  if (line.budget === null || line.remaining === null || line.used_percent === null) return null;
  const over = line.remaining.startsWith("-");
  return {
    value: money(unsigned(line.remaining)), small: `${over ? "over" : "left of"} ${money(line.budget)}`, danger: over,
    meter: { value: line.used_percent, tone: (line.tone ?? "ok") as MeterTone, label },
  };
}

const credits = (project: ProjectDetailBoardOut) => project.topups.filter((t) => t.kind === "credit" && !t.undone).length;

function TotalStat({ project }: { project: ProjectDetailBoardOut }) {
  const { total, currency } = project;
  const read = budgetStat(total, currency, "Total budget");
  const spent = formatMoney(total.spent, currency);
  if (!read) return <Stat eyebrow="Total budget" value="No total budget" sub={`${spent} spent`} />;
  const topups = credits(project);
  const extra = topups > 0 ? ` · includes ${topups} top-up${topups === 1 ? "" : "s"}` : "";
  return <Stat eyebrow="Total budget" {...read} sub={`${spent} spent · ${total.used_percent}%${extra}`} />;
}

function MonthStat({ project, today }: { project: ProjectDetailBoardOut; today: string }) {
  const { month, currency } = project;
  const eyebrow = monthLabel(today.slice(0, 7)).split(" ")[0];
  const spent = formatMoney(month.spent, currency);
  const read = budgetStat(month, currency, eyebrow);
  if (!read) return <Stat eyebrow={eyebrow} value={spent} small="spent" sub="No monthly limit" />;
  return <Stat eyebrow={eyebrow} {...read} sub={`${spent} spent this month · ${monthToGoText(today)}`} />;
}

function TasksStat({ project }: { project: ProjectDetailBoardOut }) {
  const { progress, currency } = project;
  const percent = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
  const parts: ReactNode[] = [];
  if (progress.overdue > 0) parts.push(<span key="o" className="danger">{progress.overdue} overdue</span>);
  if (progress.steps_total > 0) parts.push(`${progress.steps_done} of ${progress.steps_total} steps done`);
  if (Number(progress.planned_total) > 0) parts.push(`${formatMoney(progress.planned_total, currency)} planned`);
  return (
    <Stat eyebrow="Tasks" value={progress.done} small={`of ${progress.total} done`}
      meter={{ value: percent, tone: "accent", label: "Tasks done" }}
      sub={parts.length > 0 ? parts.flatMap((part, i) => (i === 0 ? [part] : [" · ", part])) : "Nothing planned yet"} />
  );
}

// The three numbers under the project's name (G13): total budget, this month, tasks. The server sends every
// amount, percent and tone; the only things worked out here are day counts and the tasks bar's width.
export function ProjectStats({ project, today }: { project: ProjectDetailBoardOut; today: string }) {
  return (
    <div className="p-stats">
      <TotalStat project={project} />
      <MonthStat project={project} today={today} />
      <TasksStat project={project} />
    </div>
  );
}

