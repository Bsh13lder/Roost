// A bot's chat takes the bot's colour (polish R1 follow-up): your bubbles, the send button, the composer's
// focus ring, the "New" divider, and the typing dots and caret. The colour reaches the CSS as variables on
// the chat container; the sidebar, panel and Board keep the app accent. No colour is written in a style
// sheet for this: it all comes from the avatar data.
import type { CSSProperties } from "react";

type Rgb = readonly [number, number, number];

const WHITE: Rgb = [255, 255, 255];
const DARK: Rgb = [5, 5, 5];
const READABLE = 4.5;
const HOVER_LIGHTEN = 0.12;
const PRESS_DARKEN = 0.16;
const SOFT_LIGHTEN = 0.55;   // the text-weight tint on the dark chat background
const HEX = /^#([0-9a-f]{6})$/i;

const css = ([r, g, b]: Rgb): string => `rgb(${r} ${g} ${b})`;

function parse(color: string): Rgb | null {
  const match = HEX.exec(color.trim());
  if (!match) return null;
  const n = parseInt(match[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance([r, g, b]: Rgb): number {
  const lin = (v: number) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function mix(from: Rgb, to: Rgb, amount: number): Rgb {
  return [0, 1, 2].map((i) => Math.round(from[i] + (to[i] - from[i]) * amount)) as unknown as Rgb;
}

function readable(bg: Rgb): Rgb {
  return ratio(WHITE, bg) >= ratio(DARK, bg) ? WHITE : DARK;
}

// White or near-black text, whichever is clearer on this colour (4.5:1 or better on every palette colour).
export function readableOn(color: string): string {
  const bg = parse(color);
  return css(bg ? readable(bg) : WHITE);
}

// The contrast of a "rgb(r g b)" or #hex text colour on a #hex background; for tests and checks.
export function contrastOf(text: string, background: string): number {
  const fg = parse(text) ?? (text.match(/\d+/g)?.map(Number) as unknown as Rgb);
  const bg = parse(background);
  return fg && bg ? ratio(fg, bg) : 0;
}

// The style for the chat container; empty (the app accent stays) when there is no readable colour.
export function chatAccentStyle(color: string | null | undefined): CSSProperties {
  const rgb = color ? parse(color) : null;
  if (!rgb || !color) return {};
  return {
    "--chat-accent": color.trim().toLowerCase(),
    "--chat-accent-hover": css(mix(rgb, WHITE, HOVER_LIGHTEN)),
    "--chat-accent-press": css(mix(rgb, [0, 0, 0], PRESS_DARKEN)),
    "--chat-accent-soft": css(mix(rgb, WHITE, SOFT_LIGHTEN)),
    "--chat-on-accent": css(readable(rgb)),
  } as CSSProperties;
}
