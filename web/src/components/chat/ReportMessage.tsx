import { Link } from "react-router-dom";
import { parseReport, type ReportData } from "../../lib/routineMessages";
import type { MessageOut } from "../../api/types";
import { ReminderChips } from "./ReminderCard";
import { REMINDER_FOOT, ReportFoot } from "./ReportFoot";
import { RichText } from "./RichText";

const REMINDER_SOURCE = "reminder";
const ROUTINE_SOURCES = new Set(["routine", "day_summary"]);
const ROUTINE_FALLBACK = "Routine"; // an older Report kept no routine name

function routineLabel(report: ReportData): string | null {
  if (!report.routine_id && !ROUTINE_SOURCES.has(report.source)) return null;
  return `↻ ${report.routine_name || ROUTINE_FALLBACK}`;
}

// A Report (owner, 2026-10-26: "like Grok"): what a bot says without being asked, a routine's result or a task's
// reminder, drawn as the bot's own message: its text as markdown (no raw HTML, links show their host), no headline,
// and a quiet footer: "↻ <routine> · Run log ›" or "🔔 Reminder". A single task's reminder adds four small chips
// (Done · Failed · Reschedule · Skip) and keeps its answer as a quiet line.
export function ReportMessage({ message }: { message: MessageOut }) {
  const report = parseReport(message.body);
  if (!report) return null;
  const tainted = report.tainted || message.tainted;
  const reminder = report.source === REMINDER_SOURCE;
  const botId = message.author_bot_id;
  return (
    <article className="report" aria-label={`Report: ${report.headline}`}>
      <div className="message__body report__body"><RichText text={report.text || report.headline} id={message.id} /></div>
      {reminder && report.task_id ? (
        <ReminderChips threadId={message.thread_id} messageId={message.id} taskId={report.task_id}
          answer={report.answer} answerDue={report.answer_due} tainted={tainted} />
      ) : (
        <ReportFoot label={reminder ? REMINDER_FOOT : routineLabel(report)} tainted={tainted}>
          {!reminder && botId && report.routine_id ? (
            <>
              <span aria-hidden="true">·</span>
              <Link className="report__log" aria-label="Open run log" to={`/bots/${botId}/routines/${report.routine_id}/log`}>
                Run log ›
              </Link>
            </>
          ) : null}
        </ReportFoot>
      )}
    </article>
  );
}
