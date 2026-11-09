import type { ReactNode } from "react";
import type { ComputerStepKind } from "../../api/types";

// The computer card's step marks: small 16×16 line icons, one per kind of screen step, in the current colour.
function Mark({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden="true" focusable="false" fill="none"
      stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

const MARKS: Record<ComputerStepKind, ReactNode> = {
  look: <><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" /><circle cx={8} cy={8} r={2} /></>,
  wait: <><circle cx={8} cy={8} r={6} /><path d="M8 4.8V8l2 1.4" /></>,
  scroll: <><path d="M8 2v12M5 4.5L8 2l3 2.5M5 11.5L8 14l3-2.5" /></>,
  click: <><path d="M3.5 2.5l8.5 4-3.6 1.3-1.3 3.7z" /><path d="M9 9l4 4" /></>,
  type: <><rect x={1.5} y={4} width={13} height={8} rx={1.5} /><path d="M4 7h.01M6.5 7h.01M9 7h.01M11.5 7h.01M5 9.5h6" /></>,
  key: <><rect x={2.5} y={3.5} width={11} height={9} rx={2} /><path d="M6 8h4M8.5 6.5L10 8l-1.5 1.5" /></>,
  open_page: <><circle cx={8} cy={8} r={6} /><path d="M2 8h12M8 2c1.8 1.7 2.6 3.7 2.6 6S9.8 12.3 8 14C6.2 12.3 5.4 10.3 5.4 8S6.2 3.7 8 2z" /></>,
  open_app: <><rect x={1.5} y={2.5} width={13} height={11} rx={1.5} /><path d="M1.5 5.5h13M4 4h.01M6 4h.01" /></>,
  tab: <><path d="M1.5 13.5V5a1.5 1.5 0 011.5-1.5h3.5L8 5.5h5A1.5 1.5 0 0114.5 7v6.5z" /></>,
};

export function StepMark({ kind }: { kind: ComputerStepKind }) {
  return <Mark>{MARKS[kind] ?? MARKS.look}</Mark>;
}

export function MonitorMark() {
  return <Mark><rect x={1.5} y={2.5} width={13} height={8.5} rx={1.5} /><path d="M5.5 13.5h5M8 11v2.5" /></Mark>;
}
