import type { ReactNode } from "react";
import type { RunStepKind } from "../../api/types";
import { cx } from "../../ui/cx";

// The activity pill's marks (docs/plans/2026-10-23-roost-activity-pill.md): one small line icon per kind of step,
// in the current colour. While a step runs (`moving`), its part moves calmly (styles/activity.css): the globe's
// meridian turns, the gear turns, the pointer taps, the pencil writes, the thinking dots breathe.
function Mark({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden="true" focusable="false" fill="none"
      stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

const globe = (
  <>
    <circle cx={8} cy={8} r={6} />
    <path d="M2 8h12" />
    <ellipse className="am-turn" cx={8} cy={8} rx={2.6} ry={6} />
  </>
);
const pencil = (
  <g className="am-write">
    <path d="M10.5 2.5l3 3L6 13H3v-3z" />
    <path d="M9 4l3 3" />
  </g>
);

const MARKS: Record<RunStepKind, ReactNode> = {
  think: (
    <>
      <circle className="am-dot am-dot--1" cx={4} cy={8} r={1.2} fill="currentColor" stroke="none" />
      <circle className="am-dot am-dot--2" cx={8} cy={8} r={1.2} fill="currentColor" stroke="none" />
      <circle className="am-dot am-dot--3" cx={12} cy={8} r={1.2} fill="currentColor" stroke="none" />
    </>
  ),
  search: (
    <>
      <circle cx={7} cy={7} r={4.5} />
      <path className="am-turn-small" d="M7 4.5a2.5 2.5 0 012.5 2.5" />
      <path d="M10.4 10.4L14 14" />
    </>
  ),
  read: globe,
  computer: (
    <>
      <rect x={1.5} y={2.5} width={13} height={8.5} rx={1.5} />
      <path d="M5.5 13.5h5M8 11v2.5" />
      <path className="am-tap" d="M7 5l3.5 1.6-1.4.5-.6 1.4z" fill="currentColor" stroke="none" />
    </>
  ),
  program: (
    <g className="am-spin">
      <circle cx={8} cy={8} r={2.2} />
      <path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M3.6 12.4L5 11M11 5l1.4-1.4" />
    </g>
  ),
  file: (
    <>
      <path d="M4 1.5h5l3 3v10H4z" />
      <path d="M9 1.5v3h3" />
      <path className="am-write" d="M6 9h4M6 11.5h3" />
    </>
  ),
  tasks: (
    <>
      <rect x={2} y={2} width={12} height={12} rx={3} />
      <path className="am-write" d="M5 8.2l2 2 4-4.4" />
    </>
  ),
  notes: pencil,
  message: pencil,
  money: (
    <>
      <circle cx={8} cy={8} r={6} />
      <path className="am-write" d="M10 5.6c-.5-.6-1.2-.9-2-.9-1.2 0-2 .6-2 1.5 0 2 4 1 4 3.1 0 .9-.9 1.6-2 1.6-.9 0-1.7-.4-2.1-1M8 3.6v1.1M8 11v1.2" />
    </>
  ),
  calendar: (
    <>
      <rect x={2} y={3} width={12} height={11} rx={2} />
      <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" />
      <circle className="am-dot am-dot--2" cx={8} cy={10} r={1} fill="currentColor" stroke="none" />
    </>
  ),
  bots: (
    <>
      <rect x={2} y={4} width={12} height={9} rx={4} />
      <circle className="am-dot am-dot--1" cx={6} cy={8.5} r={1} fill="currentColor" stroke="none" />
      <circle className="am-dot am-dot--3" cx={10} cy={8.5} r={1} fill="currentColor" stroke="none" />
    </>
  ),
  memory: (
    <>
      <path d="M8 14s-5.5-3.3-5.5-7.2A3 3 0 018 5a3 3 0 015.5 1.8C13.5 10.7 8 14 8 14z" />
      <path className="am-write" d="M8 5v4" />
    </>
  ),
  // A note: the bot's own words between steps (owner, 2026-11-04), a small speech bubble.
  note: (
    <>
      <path d="M3 3.5h10a1 1 0 011 1v5.5a1 1 0 01-1 1H7l-3 2.5V11H3a1 1 0 01-1-1V4.5a1 1 0 011-1z" />
      <path d="M5 6.5h6M5 8.5h4" />
    </>
  ),
  other: (
    <>
      <circle className="am-dot am-dot--1" cx={4} cy={8} r={1.1} fill="currentColor" stroke="none" />
      <circle className="am-dot am-dot--2" cx={8} cy={8} r={1.1} fill="currentColor" stroke="none" />
      <circle className="am-dot am-dot--3" cx={12} cy={8} r={1.1} fill="currentColor" stroke="none" />
    </>
  ),
};

// A finished run's line: a quiet tick in a circle.
export function DoneMark() {
  return (
    <span className="am">
      <Mark><circle cx={8} cy={8} r={6} /><path d="M5.4 8.2l1.8 1.8 3.4-3.6" /></Mark>
    </span>
  );
}

export function ActivityMark({ kind, moving = false }: { kind: RunStepKind; moving?: boolean }) {
  return (
    <span className={cx("am", moving && "am--moving")}>
      <Mark>{MARKS[kind] ?? MARKS.other}</Mark>
    </span>
  );
}
