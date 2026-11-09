import type { CSSProperties } from "react";
import { cx } from "../../ui/cx";
import { EYE_STYLES, type EyeStyle } from "./eyeStyles";
import { Glyphs, Zeds } from "./glyphs";
import { visorPieces, visorSheen, type EyePlace, type LensGeometry } from "./lensbot";

// A Lensbot's face (avatars v7 "white eyes, no glow"): a dark visor, and in it two white eyes with a
// dark pupil and a small hard highlight. No mouth, no glow. The groups nest as the motion needs them:
// lens (the zoom) → clip → pw (hidden under a glyph) → dtg (double-takes) → look (the pointer, --ex/--ey)
// → pupil (dilation). Two lids, scaled to the eye's height so every lid number is in lid units (-10.8
// open, 0 shut), close over the white: bt/bb blink, lt/lb set the status's shape. The colours are classes
// in robot.css.
const one = (value: number) => Number(value.toFixed(2));
const LID_W = 34;
const LID_H = 30;

interface EyeProps {
  place: EyePlace;
  style: EyeStyle;
  ids: FaceIds;
  glyphs: boolean;
}

export interface FaceIds {
  readonly clip: string; // the eye's own outline
  readonly sclera: string; // the white's faint top shade
}

function Lids({ style }: { style: EyeStyle }) {
  return (
    <g transform={`translate(0 ${one(style.mid)}) scale(1 ${one(style.hh / 10)})`}>
      <g className="robot__bt"><g className="robot__lt">
        <rect className="robot__lid robot__lid--top" x={-LID_W / 2} y={-LID_H} width={LID_W} height={LID_H} />
      </g></g>
      <g className="robot__bb"><g className="robot__lb">
        <rect className="robot__lid robot__lid--bottom" x={-LID_W / 2} y="0" width={LID_W} height={LID_H} />
      </g></g>
    </g>
  );
}

function Pupil({ style }: { style: EyeStyle }) {
  return (
    <g className="robot__pw"><g className="robot__dtg"><g className="robot__look"><g className="robot__pupil">
      <circle className="robot__pupil-dot" cy={style.py} r={style.pr} />
      <circle className="robot__hl robot__hl--big" cx="-1.55" cy={one(style.py - 1.75)} r="1.45" />
      <circle className="robot__hl robot__hl--small" cx="1.75" cy={one(style.py + 1.6)} r=".62" />
    </g></g></g></g>
  );
}

function Eye({ place, style, ids, glyphs }: EyeProps) {
  const vars = { "--side": place.side, "--pkx": style.pkx, "--pky": style.pky } as CSSProperties;
  return (
    <g className={cx("robot__eye", place.side < 0 ? "robot__eye--l" : "robot__eye--r")} style={vars}
      transform={`translate(${one(place.x)} ${one(place.y)}) scale(${one(place.k)})`}>
      <g className="robot__lens">
        <path className="robot__sclera" d={style.d} fill={`url(#${ids.sclera})`} />
        {style.ring ? (
          <>
            <circle className="robot__eye-ring" r="10" />
            <circle className="robot__eye-ring robot__eye-ring--dial" r="10" />
          </>
        ) : null}
        <g clipPath={`url(#${ids.clip})`}>
          <Pupil style={style} />
          {glyphs ? <Glyphs style={style} side={place.side} /> : null}
          <Lids style={style} />
        </g>
      </g>
    </g>
  );
}

/** The visor, its frame and sheen, the two eyes, and the z's when glyphs show. */
export function Face({ geometry, ids, glyphs }: { geometry: LensGeometry; ids: FaceIds; glyphs: boolean }) {
  const style = EYE_STYLES[geometry.eyeStyle];
  const pieces = visorPieces(geometry.visor);
  const sheen = visorSheen(geometry.visor);
  return (
    <g className="robot__face">
      {pieces.map((d) => <path key={`frame-${d}`} className="robot__visor-frame" d={d} />)}
      {pieces.map((d) => <path key={`visor-${d}`} className="robot__visor" d={d} />)}
      {sheen ? <path className="robot__visor-sheen" d={sheen} /> : null}
      {geometry.eyes.map((place) => <Eye key={place.side} place={place} style={style} ids={ids} glyphs={glyphs} />)}
      {glyphs ? <Zeds x={geometry.z[0]} y={geometry.z[1]} /> : null}
    </g>
  );
}

/** The defs a face needs: its eye clip and the white's shade, once per robot. */
export function FaceDefs({ geometry, ids }: { geometry: LensGeometry; ids: FaceIds }) {
  return (
    <>
      <clipPath id={ids.clip}><path d={EYE_STYLES[geometry.eyeStyle].clip} /></clipPath>
      <linearGradient id={ids.sclera} x1="0" y1="0" x2="0" y2="1">
        <stop className="robot__sclera-0" offset="0" />
        <stop className="robot__sclera-1" offset=".28" />
        <stop className="robot__sclera-2" offset="1" />
      </linearGradient>
    </>
  );
}
