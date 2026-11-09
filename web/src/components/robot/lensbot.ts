// The Lensbots (avatars v7, docs/design/robots-v7-sketch.html): eighteen soft bodies, each a row of a
// few numbers, and one pure path function. Every body samples the same 48 points, so the picker can
// morph one into the next. A dark visor across the face holds two white eyes in one of seven eye
// styles (eyeStyles.ts); its frame changes from shape to shape: a band, a pill, goggles, a screen, a
// brow or a mask. A role (roles.ts) may swap the eye style and the visor, never the body. Drawn on a
// 48-unit grid, standing on GROUND.
import type { LensbotShape } from "../../api/types";
import { EYE_STYLES, type EyeStyleId } from "./eyeStyles";

export const VIEW = 48;
export const CENTER_X = 24;
export const GROUND = 43; // the body stands here; the shadow sits just below
export const SHADOW_Y = 45;
export const POINT_COUNT = 48;
const FEET_H = 4.2;
const TOP_ROOM = 4.6;
const EYE_LINE = 0.07; // the visor's middle sits this share of the height above the body's centre
const EYE_K_MAX = 0.74;
const VISOR_MIN_W = 22;
const VISOR_MAX_W = 37;
const GOGGLE_RIM = 2.3;
const SCREEN_RADIUS = 4.6;

export type VisorKind = "band" | "pill" | "goggle" | "screen" | "brow" | "mask";

const VISORS: Readonly<Record<VisorKind, { f: number; h: number; dx: number }>> = {
  band: { f: 0.88, h: 16, dx: 0.25 }, pill: { f: 0.72, h: 15.5, dx: 0.25 }, goggle: { f: 0.8, h: 16, dx: 0.25 },
  screen: { f: 0.76, h: 19, dx: 0.24 }, brow: { f: 0.84, h: 16.5, dx: 0.25 }, mask: { f: 0.92, h: 17, dx: 0.25 },
};

type Dent = readonly [angle: number, depth: number, width: number]; // degrees from the top; a negative depth is a bump

export interface LensSpec {
  readonly id: LensbotShape;
  readonly label: string;
  readonly w: number; // width and height on the 48 grid
  readonly h: number;
  readonly nt: number; // top and bottom roundness: 2 is an ellipse, more is squarer, less is pointier
  readonly nb: number;
  readonly taper?: number; // + wider at the bottom
  readonly lean?: number;
  readonly rot?: number; // degrees
  readonly dents?: readonly Dent[];
  readonly ears?: { readonly a: number; readonly r: number; readonly kind: "side" | "round" };
  readonly feet?: boolean;
  readonly nub?: number; // a knob on top, its radius
  readonly vh?: number; // the visor's own height, for a low body
  readonly eyes: EyeStyleId;
  readonly visor: VisorKind;
}

export const LENSBOTS: readonly LensSpec[] = [
  { id: "mochi", label: "Mochi", w: 38, h: 30, nt: 2.2, nb: 3.4, taper: 0.06, eyes: "round", visor: "band" },
  { id: "loaf", label: "Loaf", w: 40, h: 27, nt: 2.1, nb: 4.4, eyes: "oval", visor: "band" },
  { id: "gumdrop", label: "Gumdrop", w: 35, h: 34, nt: 1.8, nb: 3.4, taper: 0.22, eyes: "tall", visor: "pill" },
  { id: "pebble", label: "Pebble", w: 38, h: 30, nt: 2.3, nb: 2.3, rot: -4, eyes: "ring", visor: "goggle" },
  { id: "bun", label: "Bun", w: 37, h: 30, nt: 2, nb: 2.8, dents: [[-90, 0.07, 26]], feet: true, eyes: "half", visor: "band" },
  { id: "acorn", label: "Acorn", w: 34, h: 35, nt: 2.6, nb: 1.9, taper: -0.16, eyes: "almond", visor: "brow" },
  { id: "marsh", label: "Marshmallow", w: 31, h: 36, nt: 3.3, nb: 3.3, eyes: "square", visor: "screen" },
  { id: "dumpling", label: "Dumpling", w: 42, h: 28, nt: 1.7, nb: 3.6, taper: 0.15, eyes: "half", visor: "mask" },
  { id: "muffs", label: "Muffs", w: 33, h: 32, nt: 2.4, nb: 2.8, ears: { a: 90, r: 4.6, kind: "side" }, eyes: "oval", visor: "pill" },
  { id: "squish", label: "Squish", w: 43, h: 24, nt: 2.6, nb: 2.8, vh: 14, eyes: "almond", visor: "band" },
  { id: "cub", label: "Cub", w: 36, h: 30, nt: 2.3, nb: 2.6, ears: { a: 42, r: 5, kind: "round" }, eyes: "round", visor: "goggle" },
  { id: "sprout", label: "Sprout", w: 34, h: 31, nt: 2.2, nb: 3, dents: [[-62, -0.1, 11], [-118, -0.1, 11]], eyes: "tall", visor: "pill" },
  { id: "cheeky", label: "Cheeky", w: 40, h: 30, nt: 2, nb: 2.4, dents: [[25, -0.07, 28], [155, -0.07, 28]], eyes: "round", visor: "band" },
  { id: "tower", label: "Tower", w: 28, h: 33, nt: 2.6, nb: 3.6, feet: true, eyes: "square", visor: "screen" },
  { id: "helmet", label: "Helmet", w: 38, h: 31, nt: 1.9, nb: 7, eyes: "half", visor: "mask" },
  { id: "bell", label: "Bell", w: 35, h: 33, nt: 2, nb: 5, taper: 0.3, eyes: "almond", visor: "brow" },
  { id: "puck", label: "Puck", w: 42, h: 22, nt: 3.6, nb: 3.6, feet: true, vh: 14.5, eyes: "oval", visor: "band" },
  { id: "pod", label: "Pod", w: 34, h: 32, nt: 2.4, nb: 2.4, rot: 7, nub: 2.4, eyes: "ring", visor: "goggle" },
];

export function lensSpec(shape: LensbotShape): LensSpec {
  return LENSBOTS.find((spec) => spec.id === shape) ?? LENSBOTS[0];
}

export type Point = readonly [number, number];

export interface Box {
  readonly x0: number;
  readonly x1: number;
  readonly y0: number;
  readonly y1: number;
  readonly w: number;
  readonly h: number;
}

export interface Visor {
  readonly kind: VisorKind;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
  readonly mid: number; // its middle, left to right
  readonly ey: number; // and top to bottom: the eye line
  readonly dx: number; // each eye sits this far from the middle
  readonly r: number; // a goggle lens's radius
  readonly bottom: number; // its lowest edge
}

export interface EyePlace {
  readonly x: number;
  readonly y: number;
  readonly k: number; // eye units to grid units
  readonly side: -1 | 1;
}

export interface Ear {
  readonly x: number;
  readonly y: number;
  readonly r: number;
  readonly kind: "side" | "round";
}

/** Everything one Lensbot draws: its body, the visor and the eyes in it, and what sits behind the body. */
export interface LensGeometry {
  readonly pts: readonly Point[];
  readonly d: string;
  readonly box: Box;
  readonly cy: number;
  readonly eyeY: number;
  readonly eyeStyle: EyeStyleId;
  readonly visor: Visor;
  readonly eyes: readonly EyePlace[];
  readonly z: Point; // where the Off duty z's drift up from
  readonly ears: readonly Ear[];
  readonly feet: { readonly h: number; readonly w: number } | null;
  readonly nub: { readonly x: number; readonly y: number; readonly r: number } | null;
  readonly rot: number;
}

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const two = (value: number) => Number(value.toFixed(2));

/** A closed Catmull-Rom path through the points, as cubic curves. */
export function smoothPath(pts: readonly Point[]): string {
  const count = pts.length;
  const at = (i: number) => pts[(i + count) % count];
  let d = `M${two(pts[0][0])} ${two(pts[0][1])}`;
  for (let i = 0; i < count; i += 1) {
    const [p0, p1, p2, p3] = [at(i - 1), at(i), at(i + 1), at(i + 2)];
    d += `C${two(p1[0] + (p2[0] - p0[0]) / 6)} ${two(p1[1] + (p2[1] - p0[1]) / 6)} `
      + `${two(p2[0] - (p3[0] - p1[0]) / 6)} ${two(p2[1] - (p3[1] - p1[1]) / 6)} ${two(p2[0])} ${two(p2[1])}`;
  }
  return `${d}Z`;
}

export function boxOf(pts: readonly Point[]): Box {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  return { x0, x1, y0, y1, w: x1 - x0, h: y1 - y0 };
}

function angleDiff(a: number, b: number): number {
  const d = (a - b) % (2 * Math.PI);
  if (d > Math.PI) return d - 2 * Math.PI;
  return d < -Math.PI ? d + 2 * Math.PI : d;
}

const centerYOf = (spec: LensSpec) => Math.max(spec.h / 2 + TOP_ROOM, GROUND - (spec.feet ? FEET_H : 0) - spec.h / 2);

/** The 48 points of a body, clockwise from the top. */
export function bodyPoints(spec: LensSpec): Point[] {
  const cy = centerYOf(spec);
  const pts: Point[] = [];
  for (let i = 0; i < POINT_COUNT; i += 1) {
    const t = -Math.PI / 2 + (i / POINT_COUNT) * 2 * Math.PI;
    const [c, s] = [Math.cos(t), Math.sin(t)];
    const n = s < 0 ? spec.nt : spec.nb;
    let x = Math.sign(c) * Math.abs(c) ** (2 / n) * (spec.w / 2);
    let y = Math.sign(s) * Math.abs(s) ** (2 / n) * (spec.h / 2);
    x *= 1 + (spec.taper ?? 0) * (y / (spec.h / 2));
    for (const [angle, depth, width] of spec.dents ?? []) {
      const k = depth * Math.exp(-((angleDiff(t, (angle * Math.PI) / 180) / ((width * Math.PI) / 180)) ** 2));
      x *= 1 - k;
      y *= 1 - k;
    }
    x += (spec.lean ?? 0) * (-y / (spec.h / 2));
    pts.push([CENTER_X + x, cy + y]);
  }
  return pts;
}

/** Where a level line crosses the body: its left and right x. */
export function widthAt(pts: readonly Point[], y: number): [number, number] {
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  pts.forEach((a, i) => {
    const b = pts[(i + 1) % pts.length];
    if ((a[1] - y) * (b[1] - y) > 0 || a[1] === b[1]) return;
    const x = a[0] + ((y - a[1]) / (b[1] - a[1])) * (b[0] - a[0]);
    low = Math.min(low, x);
    high = Math.max(high, x);
  });
  return high > low ? [low, high] : [CENTER_X - 10, CENTER_X + 10];
}

function visorLayout(spec: LensSpec, kind: VisorKind, eyeStyle: EyeStyleId, pts: readonly Point[], cy: number) {
  const numbers = VISORS[kind];
  const style = EYE_STYLES[eyeStyle];
  const ey = cy - spec.h * EYE_LINE;
  const [left, right] = widthAt(pts, ey);
  const mid = (left + right) / 2;
  const w = clamp((right - left) * numbers.f, VISOR_MIN_W, VISOR_MAX_W);
  const h = spec.vh ?? numbers.h;
  const dx = w * numbers.dx;
  const k = Math.min((h / 2 - 1.5) / style.hh, (dx - 1.2) / style.hw, EYE_K_MAX);
  const r = Math.max(style.hw, style.hh) * k + GOGGLE_RIM;
  const y = ey - h / 2;
  const bottom = kind === "goggle" ? ey + r : y + h;
  const visor: Visor = { kind, x: mid - w / 2, y, w, h, mid, ey, dx, r, bottom };
  const eyes: EyePlace[] = ([-1, 1] as const).map((side) => ({ x: mid + side * dx, y: ey - style.mid * k, k, side }));
  const z: Point = [mid + dx + style.hw * k * 0.7, y - 2.6];
  return { visor, eyes, z };
}

function earsOf(spec: LensSpec, pts: readonly Point[], cy: number): Ear[] {
  if (!spec.ears) return [];
  const { a, r, kind } = spec.ears;
  const inset = kind === "side" ? -0.12 : 0.35; // muffs sit on the outside; round ears tuck in
  return [-1, 1].map((side) => {
    const index = (Math.round(((side * a) / 360) * POINT_COUNT) + POINT_COUNT) % POINT_COUNT;
    const [px, py] = pts[index];
    const [dx, dy] = [px - CENTER_X, py - cy];
    const d = Math.hypot(dx, dy) || 1;
    return { x: px - (dx / d) * r * inset, y: py - (dy / d) * r * inset, r, kind };
  });
}

export interface LookNudge {
  readonly eyes?: EyeStyleId;
  readonly visor?: VisorKind;
}

const cache = new Map<string, LensGeometry>();

/** A shape's geometry, with a role's eye style and visor when it brings them. Computed once for each. */
export function lensGeometry(spec: LensSpec, nudge: LookNudge = {}): LensGeometry {
  const eyeStyle = nudge.eyes ?? spec.eyes;
  const kind = nudge.visor ?? spec.visor;
  const key = `${spec.id}|${eyeStyle}|${kind}`;
  const known = cache.get(key);
  if (known) return known;
  const cy = centerYOf(spec);
  const pts = bodyPoints(spec);
  const { visor, eyes, z } = visorLayout(spec, kind, eyeStyle, pts, cy);
  const geometry: LensGeometry = {
    pts, d: smoothPath(pts), box: boxOf(pts), cy, eyeY: visor.ey, eyeStyle, visor, eyes, z,
    ears: earsOf(spec, pts, cy),
    feet: spec.feet ? { h: FEET_H, w: spec.w } : null,
    nub: spec.nub ? { x: pts[0][0], y: pts[0][1] - spec.nub * 0.35, r: spec.nub } : null,
    rot: spec.rot ?? 0,
  };
  cache.set(key, geometry);
  return geometry;
}

const mix = (a: number, b: number, t: number) => a + (b - a) * t;

/** Part way from `a` to `b` (the picker's morph): the body tweens; the face is already the new one. */
export function blendGeometry(a: LensGeometry, b: LensGeometry, t: number): LensGeometry {
  if (t >= 1) return b;
  const pts: Point[] = a.pts.map((p, i) => [mix(p[0], b.pts[i][0], t), mix(p[1], b.pts[i][1], t)]);
  return { ...b, pts, d: smoothPath(pts), box: boxOf(pts), cy: mix(a.cy, b.cy, t), eyeY: mix(a.eyeY, b.eyeY, t), rot: mix(a.rot, b.rot, t) };
}

const circle = (cx: number, cy: number, r: number) =>
  `M${two(cx - r)} ${two(cy)}A${two(r)} ${two(r)} 0 1 0 ${two(cx + r)} ${two(cy)}A${two(r)} ${two(r)} 0 1 0 ${two(cx - r)} ${two(cy)}Z`;

export function roundRect(x: number, y: number, w: number, h: number, radius: number): string {
  const r = Math.min(radius, w / 2, h / 2);
  return `M${two(x + r)} ${two(y)}H${two(x + w - r)}A${two(r)} ${two(r)} 0 0 1 ${two(x + w)} ${two(y + r)}`
    + `V${two(y + h - r)}A${two(r)} ${two(r)} 0 0 1 ${two(x + w - r)} ${two(y + h)}H${two(x + r)}`
    + `A${two(r)} ${two(r)} 0 0 1 ${two(x)} ${two(y + h - r)}V${two(y + r)}A${two(r)} ${two(r)} 0 0 1 ${two(x + r)} ${two(y)}Z`;
}

function browPath({ x, y, w, h }: Visor): string {
  const r = h / 2;
  return `M${two(x + 2.2)} ${two(y)}H${two(x + w - 2.2)}Q${two(x + w)} ${two(y)} ${two(x + w)} ${two(y + 2.2)}`
    + `V${two(y + h - r)}A${two(r)} ${two(r)} 0 0 1 ${two(x + w - r)} ${two(y + h)}H${two(x + r)}`
    + `A${two(r)} ${two(r)} 0 0 1 ${two(x)} ${two(y + h - r)}V${two(y + 2.2)}Q${two(x)} ${two(y)} ${two(x + 2.2)} ${two(y)}Z`;
}

function maskPath({ x, y, w, h, mid }: Visor): string {
  return `M${two(x)} ${two(y + 3.4)}Q${two(mid)} ${two(y - 3.2)} ${two(x + w)} ${two(y + 3.4)}`
    + `Q${two(x + w + 1.4)} ${two(y + h / 2 + 1)} ${two(x + w - 1.6)} ${two(y + h - 2.2)}`
    + `Q${two(mid)} ${two(y + h + 2.6)} ${two(x + 1.6)} ${two(y + h - 2.2)}`
    + `Q${two(x - 1.4)} ${two(y + h / 2 + 1)} ${two(x)} ${two(y + 3.4)}Z`;
}

/** The visor's outline as closed paths: two lenses and a bridge for goggles, one piece for the rest. */
export function visorPieces(visor: Visor): string[] {
  const { kind, x, y, w, h, mid, ey, dx, r } = visor;
  if (kind === "goggle") {
    return [circle(mid - dx, ey, r), circle(mid + dx, ey, r), roundRect(mid - dx, ey - r * 0.42, dx * 2, r * 0.84, 0)];
  }
  if (kind === "brow") return [browPath(visor)];
  if (kind === "mask") return [maskPath(visor)];
  return [roundRect(x, y, w, h, kind === "screen" ? SCREEN_RADIUS : h / 2)];
}

/** The thin sheen along the top of a visor (goggles have none). */
export function visorSheen({ kind, x, y, w, h }: Visor): string | null {
  return kind === "goggle" ? null : `M${two(x + h * 0.45)} ${two(y + 1.3)}H${two(x + w - h * 0.45)}`;
}
