import type { BotStatus } from "../../api/types";

// What a Lensbot shows (avatars v7): the five statuses as postures, the lids they set, the glyph in the
// eye field, and the events that play once on top (robot.css holds the motion for each).
export type RobotMoment = "rest" | "onit" | "ask" | "stuck" | "off";

export const ROBOT_MOMENTS: readonly RobotMoment[] = ["rest", "onit", "ask", "stuck", "off"];

export const STATUS_MOMENT: Readonly<Record<BotStatus, RobotMoment>> = {
  resting: "rest", on_it: "onit", asking_you: "ask", stuck: "stuck", off_duty: "off",
};

// The lids: open, wide (Asking you, a poke, Created something, New message), focus (Thinking),
// narrow, sad (Stuck: the left lid droops), happy (Done) and closed (Off duty: lines).
export type RobotFaceLids = "open" | "wide" | "focus" | "narrow" | "sad" | "happy" | "closed";

export const MOMENT_FACE: Readonly<Record<RobotMoment, RobotFaceLids>> = {
  rest: "open", onit: "open", ask: "wide", stuck: "sad", off: "closed",
};

// The glyph in the eye field: a scanning bar across both eyes while On it, three dots while thinking,
// a "?" (Asking you), an "!" (Stuck), a cursor (waiting for you to take control), an envelope (a new
// message) and a check (Done) in the right eye, the z's (Off duty). Dark ink on white, so each reads
// as a shape, not a colour.
export type RobotGlyph = "" | "onit" | "think" | "ask" | "stuck" | "ctrl" | "msg" | "done" | "off";

export const MOMENT_GLYPH: Readonly<Record<RobotMoment, RobotGlyph>> = {
  rest: "", onit: "onit", ask: "ask", stuck: "stuck", off: "off",
};

// Every event that plays once: from live data (created, done, msg, stuck), from the pointer (dbl, around)
// and the idle life (dblblink, saccade, camera, tilt, whirr, hmm). A poke is a click.
export type RobotEvent =
  | "created" | "done" | "msg" | "stuck"
  | "dbl" | "around"
  | "dblblink" | "saccade" | "camera" | "tilt" | "whirr" | "hmm";

// How long each plays, in ms: the class stays on the SVG this long.
export const EVENT_MS: Readonly<Record<RobotEvent | "poke", number>> = {
  created: 1500, done: 2800, msg: 2600, stuck: 2700,
  dbl: 1100, around: 1800,
  dblblink: 800, saccade: 600, camera: 1900, tilt: 2600, whirr: 1400, hmm: 2300,
  poke: 800,
};

// The lids and the glyph an event sets while it plays; the others keep the status's.
export const EVENT_FACE: Readonly<Partial<Record<RobotEvent, RobotFaceLids>>> = {
  created: "wide", done: "happy", msg: "wide", stuck: "sad",
};
export const EVENT_GLYPH: Readonly<Partial<Record<RobotEvent, RobotGlyph>>> = { done: "done", msg: "msg" };

// A keyed event: the same event twice is two keys, so it plays twice.
export interface RobotEventIn {
  readonly name: RobotEvent;
  readonly key: number;
}

// Owner, 2026-10-27: while a bot works, its eyes act out what it is doing (robot-doing.css): thinking shows
// the dots, searching scans side to side, reading sweeps along lines, the computer looks down at a screen and
// taps, writing looks down and moves with the pen, records glance down and nod, a program whirrs.
export type RobotDoing = "think" | "search" | "read" | "computer" | "write" | "records" | "program";

// The activity pill's step kinds (api RunStepKind) as what the eyes do.
export const DOING_OF_KIND: Readonly<Record<string, RobotDoing>> = {
  think: "think", other: "think", note: "think", search: "search", read: "read", computer: "computer", program: "program",
  file: "write", notes: "write", message: "write", memory: "write",
  tasks: "records", money: "records", calendar: "records", bots: "records",
};

export function doingOf(kind: string | null | undefined): RobotDoing {
  return (kind && DOING_OF_KIND[kind]) || "think";
}

export interface FaceState {
  readonly moment: RobotMoment;
  readonly playing: RobotEvent | null;
  readonly thinking: boolean;
  readonly poked: boolean;
  readonly control: boolean;
  readonly doing?: RobotDoing | null;
}

/** The lids: a poke widens open eyes, an event sets its own, thinking focuses open eyes, else the status's. */
export function lidsFor({ moment, playing, thinking, poked }: FaceState): RobotFaceLids {
  if (poked && moment !== "off" && moment !== "stuck") return "wide";
  const eventLids = playing ? EVENT_FACE[playing] : undefined;
  if (eventLids) return eventLids;
  if (thinking && MOMENT_FACE[moment] === "open") return "focus";
  return MOMENT_FACE[moment];
}

/** The glyph: an event's own while it plays, then what it is doing (only thinking and a program keep a glyph;
 *  the others show the pupils, which move), then thinking, then a wait for Take control, else the status's. */
export function glyphFor({ moment, playing, thinking, control, doing }: FaceState): RobotGlyph {
  const eventGlyph = playing ? EVENT_GLYPH[playing] : undefined;
  if (eventGlyph) return eventGlyph;
  if (doing && moment !== "off") return doing === "think" ? "think" : doing === "program" ? "onit" : "";
  if (thinking && moment !== "off") return "think";
  if (control) return "ctrl";
  return MOMENT_GLYPH[moment];
}
