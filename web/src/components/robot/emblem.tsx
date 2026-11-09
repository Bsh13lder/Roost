import type { ReactElement } from "react";
import type { BotRole } from "../../api/types";
import type { LensGeometry } from "./lensbot";

// Role looks (avatars v7): a small, clean emblem built into the body, never an antenna. Most are a tiny
// plate on the lower body, under the visor; code is a "</>" on the visor frame and SEO a magnifier lens
// on the side. The plate is the bot's colour, lighter, and the mark on it a deeper shade of the same;
// no glow. Drawn on a 10-unit box and scaled to the room the body has. Below EMBLEM_MIN_PX only the
// shape and the colour remain.
export const EMBLEM_MIN_PX = 32;
const PLATE_MIN = 4.4;
const PLATE_MAX = 7.2;
const PLATE_SHARE = 0.62; // of the room between the visor and the bottom of the body
const BOX = 10;
const SIDE_LENS = 6;

const one = (value: number) => Number(value.toFixed(2));

function TasksMark() {
  return (
    <>
      <rect className="robot__emblem-plate" x="-5" y="-4" width="10" height="8" rx="2" />
      <path className="robot__emblem-mark" d="M-2.6 .1L-.7 2L2.8 -1.8" strokeWidth="1.5" />
    </>
  );
}

function MoneyMark() {
  return (
    <>
      <circle className="robot__emblem-plate" r="4.6" />
      <circle className="robot__emblem-mark" r="3.1" strokeWidth=".8" />
      <path className="robot__emblem-mark" d="M0 -1.7V1.7" strokeWidth="1.3" />
    </>
  );
}

function SocialMark() {
  return (
    <>
      <path className="robot__emblem-plate"
        d="M-3 -4H3A2 2 0 0 1 5 -2V.4A2 2 0 0 1 3 2.4H-.4L-3 4.6V2.4A2 2 0 0 1 -5 .4V-2A2 2 0 0 1 -3 -4Z" />
      {[-2, 0, 2].map((x) => <circle key={x} className="robot__emblem-dot" cx={x} cy="-.8" r=".75" />)}
    </>
  );
}

function ResearchMark() {
  return (
    <>
      <path className="robot__emblem-plate" d="M-3.8 -4.8H1.4L3.8 -2.4V4.8H-3.8Z" />
      <path className="robot__emblem-mark" d="M1.4 -4.8V-2.4H3.8M-2.1 -.6H2.1M-2.1 1.4H2.1M-2.1 3.2H.8" strokeWidth=".8" />
    </>
  );
}

function WriterMark() {
  return (
    <>
      <path className="robot__emblem-plate" d="M0 4.9L3.5 -.4L1.9 -4.6H-1.9L-3.5 -.4Z" />
      <path className="robot__emblem-mark" d="M0 4.4V.6" strokeWidth=".8" />
      <circle className="robot__emblem-dot" cy="-.1" r=".95" />
    </>
  );
}

function CodeMark() {
  return <path className="robot__emblem-mark robot__emblem-mark--light" d="M-2.3 -2.2L-4.5 0L-2.3 2.2M2.3 -2.2L4.5 0L2.3 2.2M.9 -2.8L-.9 2.8" strokeWidth="1.4" />;
}

function SeoMark() {
  return (
    <>
      <path className="robot__emblem-mark robot__emblem-mark--light" d="M2.1 2.1L4.6 4.6" strokeWidth="1.9" />
      <circle className="robot__emblem-plate" r="3.2" />
      <circle className="robot__emblem-glass" r="2" />
    </>
  );
}

const MARKS: Readonly<Record<Exclude<BotRole, "general">, () => ReactElement>> = {
  tasks: TasksMark, code: CodeMark, seo: SeoMark, money: MoneyMark, social: SocialMark, research: ResearchMark,
  writer: WriterMark,
};

/** Where the emblem sits and how big: under the visor, on the visor's lower edge, or on the right side. */
function placeOf(role: Exclude<BotRole, "general">, geometry: LensGeometry): { x: number; y: number; size: number } {
  const { visor, box, cy } = geometry;
  const room = Math.max(0, box.y1 - visor.bottom);
  const size = Math.min(PLATE_MAX, Math.max(PLATE_MIN, room * PLATE_SHARE));
  if (role === "code") return { x: visor.mid, y: visor.bottom + size * 0.42, size };
  if (role === "seo") return { x: box.x1 - SIDE_LENS * 0.55, y: cy + (box.y1 - cy) * 0.36, size: SIDE_LENS };
  return { x: visor.mid, y: visor.bottom + Math.max(size * 0.55, room / 2), size };
}

export function RoleEmblem({ role, geometry }: { role: BotRole; geometry: LensGeometry }) {
  if (role === "general") return null;
  const Mark = MARKS[role];
  const { x, y, size } = placeOf(role, geometry);
  return (
    <g className={`robot__emblem robot__emblem--${role}`} data-role={role} aria-hidden="true"
      transform={`translate(${one(x)} ${one(y)}) scale(${one(size / BOX)})`}>
      <Mark />
    </g>
  );
}
