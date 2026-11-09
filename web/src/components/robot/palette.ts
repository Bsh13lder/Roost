// The robots' colours (redesign V1, kept for the Lensbots). Colour data, not styling: tokens.test.ts allows this file.
import type { LensbotShape } from "../../api/types";
import { LENSBOT_SHAPES } from "./look";

// The editor's twelve swatches.
export const ROBOT_COLORS: ReadonlyArray<readonly [string, string]> = [
  ["#8b5cf6", "Violet"], ["#3b82f6", "Blue"], ["#14b8a6", "Teal"], ["#22c55e", "Green"], ["#f97316", "Orange"],
  ["#ec4899", "Pink"], ["#ef4444", "Red"], ["#eab308", "Yellow"], ["#6366f1", "Indigo"], ["#84cc16", "Lime"],
  ["#ffffff", "White"], ["#9ca3af", "Grey"],
];

// A new bot takes the first of these no teammate wears (roost/constants.py BOT_DEFAULT_COLORS, the
// same list: tests/test_bot_look.py compares them). One entry per line.
export const BOT_DEFAULT_COLORS: readonly string[] = [
  "#8b5cf6",
  "#3b82f6",
  "#14b8a6",
  "#22c55e",
  "#f97316",
  "#ec4899",
  "#ef4444",
  "#eab308",
  "#6366f1",
  "#84cc16",
];

export function nextBotColor(used: readonly string[]): string {
  const worn = new Set(used.map((color) => color.toLowerCase()));
  const free = BOT_DEFAULT_COLORS.find((color) => !worn.has(color));
  return free ?? BOT_DEFAULT_COLORS[used.length % BOT_DEFAULT_COLORS.length];
}

function channels(hex: string): [number, number, number] {
  const number = Number.parseInt(hex.slice(1), 16);
  return [(number >> 16) & 255, (number >> 8) & 255, number & 255];
}

const rgb = ([red, green, blue]: number[]) => `rgb(${red}, ${green}, ${blue})`;
const clamp = (value: number) => Math.max(0, Math.min(255, Math.round(value)));

/** Lighter: mixed `amount` (0..1) of the way to white. Signals glow in the bot's colour, tinted. */
export function tint(hex: string, amount: number): string {
  return rgb(channels(hex).map((value) => clamp(value + (255 - value) * amount)));
}

/** Darker: each channel times `factor` (0..1). The body's deep edge. */
export function shade(hex: string, factor: number): string {
  return rgb(channels(hex).map((value) => clamp(value * factor)));
}

export interface SurpriseLook {
  shape: LensbotShape;
  color: string;
}

function pickOther<T>(items: readonly T[], current: T, random: () => number): T {
  const others = items.filter((item) => item !== current);
  return others[Math.floor(random() * others.length) % others.length];
}

/** "Surprise me": a new shape and a new colour, each different from now. */
export function surpriseLook(current: SurpriseLook, random: () => number = Math.random): SurpriseLook {
  const colors = ROBOT_COLORS.map(([color]) => color);
  return {
    shape: pickOther(LENSBOT_SHAPES, current.shape, random),
    color: pickOther(colors, current.color.toLowerCase(), random),
  };
}
