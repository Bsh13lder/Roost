// The seven eye styles of the Lensbots (avatars v7, docs/design/robots-v7-sketch.html): a white sclera,
// a dark pupil and a small hard highlight, drawn in eye units (about ten across the half width) and
// scaled into the visor. top/bot: the white's extent; hw: its half width; pr/py: the pupil's radius and
// offset; pkx/pky: how far the pupil travels; gs: the glyph scale. The lids and glyphs clip to `clip`
// (the ring lens) or to the white itself.
export type EyeStyleId = "round" | "oval" | "tall" | "square" | "half" | "almond" | "ring";

export interface EyeStyle {
  readonly label: string;
  readonly d: string;
  readonly clip: string;
  readonly top: number;
  readonly bot: number;
  readonly hw: number;
  readonly pr: number;
  readonly py: number;
  readonly pkx: number;
  readonly pky: number;
  readonly gs: number;
  readonly ring: boolean;
  readonly mid: number; // the middle of the white, top to bottom
  readonly hh: number; // its half height
}

type EyeNumbers = Omit<EyeStyle, "mid" | "hh" | "clip" | "py" | "ring"> & { clip?: string; py?: number; ring?: boolean };

const ell = (rx: number, ry: number) => `M${-rx} 0A${rx} ${ry} 0 1 0 ${rx} 0A${rx} ${ry} 0 1 0 ${-rx} 0Z`;

function softSquare(hw: number, hh: number, r: number): string {
  const k = r * 0.45;
  return `M${-hw + r} ${-hh}H${hw - r}C${hw - k} ${-hh} ${hw} ${-hh + k} ${hw} ${-hh + r}V${hh - r}`
    + `C${hw} ${hh - k} ${hw - k} ${hh} ${hw - r} ${hh}H${-hw + r}C${-hw + k} ${hh} ${-hw} ${hh - k} ${-hw} ${hh - r}`
    + `V${-hh + r}C${-hw} ${-hh + k} ${-hw + k} ${-hh} ${-hw + r} ${-hh}Z`;
}

function style(numbers: EyeNumbers): EyeStyle {
  return {
    ...numbers,
    clip: numbers.clip ?? numbers.d,
    py: numbers.py ?? 0,
    ring: numbers.ring ?? false,
    mid: (numbers.top + numbers.bot) / 2,
    hh: (numbers.bot - numbers.top) / 2,
  };
}

export const EYE_STYLE_IDS: readonly EyeStyleId[] = ["round", "oval", "tall", "square", "half", "almond", "ring"];

export const EYE_STYLES: Readonly<Record<EyeStyleId, EyeStyle>> = {
  round: style({ label: "Round", d: ell(10, 10), top: -10, bot: 10, hw: 10, pr: 4.4, pkx: 2.6, pky: 2.6, gs: 0.95 }),
  oval: style({ label: "Oval", d: ell(10.8, 7.8), top: -7.8, bot: 7.8, hw: 10.8, pr: 4, pkx: 3.3, pky: 1.6, gs: 0.76 }),
  tall: style({ label: "Tall oval", d: ell(7.4, 11.2), top: -11.2, bot: 11.2, hw: 7.4, pr: 3.9, pkx: 1.6, pky: 3.4, gs: 0.74 }),
  square: style({ label: "Soft square", d: softSquare(9.2, 9.2, 5), top: -9.2, bot: 9.2, hw: 9.2, pr: 4.2, pkx: 2.5, pky: 2.5, gs: 0.9 }),
  half: style({
    label: "Half-moon", d: "M-10 -2.6C-5 -4.6 5 -4.6 10 -2.6A10.4 10.4 0 1 1 -10 -2.6Z",
    top: -4.1, bot: 10.7, hw: 10.4, pr: 4.1, py: 3.4, pkx: 2.7, pky: 1.3, gs: 0.7,
  }),
  almond: style({
    label: "Wide almond", d: "M-12.6 0C-7.8 -9.6 7.8 -9.6 12.6 0C7.8 9.6 -7.8 9.6 -12.6 0Z",
    top: -7.2, bot: 7.2, hw: 12.6, pr: 3.9, pkx: 3.8, pky: 1, gs: 0.66,
  }),
  ring: style({
    label: "Ring lens", d: ell(8.4, 8.4), clip: ell(11.1, 11.1),
    top: -11.1, bot: 11.1, hw: 11.1, pr: 3.7, pkx: 2.1, pky: 2.1, gs: 0.8, ring: true,
  }),
};
