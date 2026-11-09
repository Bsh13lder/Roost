import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties } from "react";
import type { BotRole, LensbotShape } from "../../api/types";
import { cx } from "../../ui/cx";
import { EMBLEM_MIN_PX, RoleEmblem } from "./emblem";
import { Face, FaceDefs } from "./eyes";
import { CENTER_X, GROUND, SHADOW_Y, VIEW, lensGeometry, lensSpec, type LensGeometry } from "./lensbot";
import { LIVE_OVER_PX } from "./lookAt";
import { EVENT_MS, glyphFor, lidsFor, type RobotDoing, type RobotEventIn, type RobotMoment } from "./moments";
import { shade, tint } from "./palette";
import { ROLE_LOOKS } from "./roles";
import { useLookAt } from "./useLookAt";
import { useMorph } from "./useMorph";

const one = (value: number) => Number(value.toFixed(2));
const BLINK_SECONDS: readonly [number, number] = [5.2, 8];
const BLINK_SPREAD_SECONDS = 6;
const IDLE_SPREAD_SECONDS = 4;
// The bot's colour, mixed: the skin's light and deep ends, the visor's frame, the ears' insides, the
// feet, the nub, the ring lens, the Created pulse, and the role emblem's plate and mark.
const TONES: ReadonlyArray<readonly [string, "tint" | "shade", number]> = [
  ["--bot-light", "tint", 0.34], ["--bot-deep", "shade", 0.72], ["--bot-frame", "shade", 0.5],
  ["--bot-inner", "shade", 0.8], ["--bot-feet", "shade", 0.74], ["--bot-nub", "tint", 0.18], ["--bot-ring", "tint", 0.3],
  ["--bot-pulse", "tint", 0.5], ["--bot-emblem", "tint", 0.55], ["--bot-emblem-ink", "shade", 0.42],
];

export interface RobotFaceProps {
  shape: LensbotShape;
  color: string; // "#RRGGBB"
  role?: BotRole; // the job's emblem; general wears none
  moment?: RobotMoment; // the status's posture
  star?: boolean; // the main bot
  size?: number; // px
  title?: string; // the accessible name; without one the drawing is hidden from assistive tech
  still?: boolean; // no motion: the user prefers reduced motion
  picture?: string | null; // the bot's own picture, inside the body
  pictureEyes?: boolean; // the visor and eyes on top of the picture (off by default)
  event?: RobotEventIn | null; // a keyed event that plays once
  thinking?: boolean; // a run has started and no text has come yet
  control?: boolean; // waiting for you to take control: a cursor in its eye
  poke?: boolean; // a click squishes it: the panel hero and the pinned tiles (never a focus stop of its own)
  doing?: RobotDoing | null; // working: the eyes act out what it is doing (robot-doing.css)
  className?: string;
}

// The first and last frames spread a team's blinks and bobs so they never move in step.
function useSpread() {
  return useState(() => ({
    "--blink-dur": `${one(BLINK_SECONDS[0] + Math.random() * (BLINK_SECONDS[1] - BLINK_SECONDS[0]))}s`,
    "--blink-delay": `${one(-Math.random() * BLINK_SPREAD_SECONDS)}s`,
    "--idle-delay": `${one(-Math.random() * IDLE_SPREAD_SECONDS)}s`,
  }))[0];
}

// A keyed event plays once, for its length; the same key again does nothing.
function usePlayedEvent(event: RobotEventIn | null | undefined) {
  const [playing, setPlaying] = useState<RobotEventIn["name"] | null>(null);
  const lastKey = useRef<number | null>(null);
  const name = event?.name;
  const key = event?.key;
  useEffect(() => {
    if (!name || key === undefined || key === lastKey.current) return undefined;
    lastKey.current = key;
    setPlaying(name);
    const timer = setTimeout(() => setPlaying(null), EVENT_MS[name]);
    return () => clearTimeout(timer);
  }, [name, key]);
  return playing;
}

function usePoke(enabled: boolean): [boolean, () => void] {
  const [poked, setPoked] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current !== null) clearTimeout(timer.current); }, []);
  const poke = useCallback(() => {
    if (!enabled) return;
    setPoked(true);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPoked(false), EVENT_MS.poke);
  }, [enabled]);
  return [poked, poke];
}

const STAR_POINTS = Array.from({ length: 10 }, (_, i) => {
  const angle = -Math.PI / 2 + (i * Math.PI) / 5;
  const radius = i % 2 ? 2.4 : 5.4;
  return `${one(41 + Math.cos(angle) * radius)} ${one(8 + Math.sin(angle) * radius)}`;
});

function Star() {
  return <g className="robot__star"><path className="robot__star-mark" d={`M${STAR_POINTS.join("L")}Z`} /></g>;
}

/** What sits behind the skin: ears, a nub, feet. */
function Back({ geometry, skin }: { geometry: LensGeometry; skin: string }) {
  return (
    <>
      {geometry.feet ? [-1, 1].map((side) => (
        <rect key={side} className="robot__foot" x={one(CENTER_X + side * geometry.feet!.w * 0.22 - 3.6)}
          y={one(GROUND - geometry.feet!.h - 3)} width="7.2" height={one(geometry.feet!.h + 3)} rx="3" />
      )) : null}
      {geometry.ears.map((ear) => (
        <g key={ear.x} className="robot__ear">
          {ear.kind === "side" ? (
            <>
              <rect x={one(ear.x - ear.r * 0.65)} y={one(ear.y - ear.r * 1.3)} width={one(ear.r * 1.3)} height={one(ear.r * 2.6)}
                rx={one(ear.r * 0.65)} fill={`url(#${skin})`} />
              <rect className="robot__ear-inner" x={one(ear.x - ear.r * 0.3)} y={one(ear.y - ear.r * 0.8)} width={one(ear.r * 0.6)}
                height={one(ear.r * 1.6)} rx={one(ear.r * 0.3)} />
            </>
          ) : (
            <>
              <circle cx={one(ear.x)} cy={one(ear.y)} r={ear.r} fill={`url(#${skin})`} />
              <circle className="robot__ear-inner" cx={one(ear.x)} cy={one(ear.y)} r={one(ear.r * 0.5)} />
            </>
          )}
        </g>
      ))}
      {geometry.nub ? <circle className="robot__nub" cx={one(geometry.nub.x)} cy={one(geometry.nub.y)} r={geometry.nub.r} /> : null}
    </>
  );
}

function Skin({ geometry, ids, picture }: { geometry: LensGeometry; ids: Ids; picture: string | null }) {
  const { box } = geometry;
  if (picture) {
    return (
      <>
        <image className="robot__picture" href={picture} x={one(box.x0)} y={one(box.y0)} width={one(box.w)} height={one(box.h)}
          preserveAspectRatio="xMidYMid slice" clipPath={`url(#${ids.clip})`} />
        <path className="robot__rim" d={geometry.d} />
      </>
    );
  }
  const [sx, sy] = [box.x0 + box.w * 0.32, box.y0 + box.h * 0.2];
  return (
    <>
      <path className="robot__skin" d={geometry.d} fill={`url(#${ids.skin})`} />
      <ellipse className="robot__sheen" cx={one(sx)} cy={one(sy)} rx={one(box.w * 0.16)} ry={one(box.h * 0.08)}
        transform={`rotate(-22 ${one(sx)} ${one(sy)})`} />
    </>
  );
}

interface Ids {
  readonly skin: string;
  readonly clip: string;
  readonly eyeClip: string;
  readonly sclera: string;
}

function Defs({ geometry, ids, face }: { geometry: LensGeometry; ids: Ids; face: boolean }) {
  return (
    <defs>
      <radialGradient id={ids.skin} cx=".36" cy=".26" r=".9">
        <stop className="robot__skin-0" offset="0" />
        <stop className="robot__skin-1" offset=".55" />
        <stop className="robot__skin-2" offset="1" />
      </radialGradient>
      <clipPath id={ids.clip}><path d={geometry.d} /></clipPath>
      {face ? <FaceDefs geometry={geometry} ids={{ clip: ids.eyeClip, sclera: ids.sclera }} /> : null}
    </defs>
  );
}

function cssVars(geometry: LensGeometry, color: string, spread: Record<string, string>): CSSProperties {
  const vars: Record<string, string> = { "--bot": color, "--oy": `${one(GROUND)}px`, ...spread };
  for (const [name, kind, amount] of TONES) vars[name] = kind === "tint" ? tint(color, amount) : shade(color, amount);
  vars["--cy"] = `${one(geometry.cy)}px`;
  return vars as CSSProperties;
}

// A Lensbot (avatars v7): one stateful SVG. data-moment is its status, data-face its lids, data-g the
// glyph in its eyes, a class an event in flight; robot.css holds every motion. Groups, outside in: pose
// (the status's posture), float (the idle breath), evt (events), lean (the pointer tilt and hover), body
// (the shape's own tilt). The shared pointer loop (lookAt.ts) moves the eyes of a live robot: one drawn
// larger than 32 px, with its eyes showing. Glyphs show above 32 px; the role emblem from 32 px up.
export function RobotFace({
  shape, color, role = "general", moment = "rest", star = false, size = 96, title, still = false, picture = null,
  pictureEyes = false, event = null, thinking = false, control = false, poke = false, doing = null, className,
}: RobotFaceProps) {
  const ref = useRef<SVGSVGElement>(null);
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const target = useMemo(() => lensGeometry(lensSpec(shape), ROLE_LOOKS[role] ?? {}), [shape, role]);
  const face = !picture || pictureEyes;
  const big = size > LIVE_OVER_PX;
  const live = big && face && !still;
  const { geometry, morphing } = useMorph(target, live);
  const spread = useSpread();
  const playing = usePlayedEvent(event);
  const [poked, doPoke] = usePoke(poke);
  useLookAt(ref, live);
  const state = { moment, playing, thinking, poked, control, doing };
  const ids: Ids = { skin: `robot-skin-${id}`, clip: `robot-clip-${id}`, eyeClip: `robot-eye-${id}`, sclera: `robot-sclera-${id}` };
  const a11y = title ? { role: "img", "aria-label": title } : { "aria-hidden": true, focusable: false };
  const classes = cx("robot", live ? "robot--live" : "robot--xs", still && "robot--still", morphing && "robot--morph",
    poked && "robot--poked", playing && `robot--ev-${playing}`, thinking && "robot--ev-think", className);
  return (
    <svg ref={ref} className={classes} width={size} height={size} viewBox={`0 0 ${VIEW} ${VIEW}`}
      data-shape={shape} data-role={role} data-eyes={geometry.eyeStyle} data-visor={geometry.visor.kind} data-moment={moment}
      data-doing={doing ?? undefined} data-face={lidsFor(state)} data-g={glyphFor(state)} data-ey={one(geometry.eyeY)} style={cssVars(geometry, color, spread)}
      onClick={poke ? doPoke : undefined} {...a11y}>
      <Defs geometry={geometry} ids={ids} face={face} />
      <ellipse className="robot__shadow" cx={CENTER_X} cy={SHADOW_Y} rx={one(geometry.box.w * 0.36)} ry="1.6" />
      <g className="robot__pose"><g className="robot__float"><g className="robot__evt">
        <ellipse className="robot__pulse" cx={CENTER_X} cy={one(geometry.cy)} rx={one(geometry.box.w / 2 + 1)} ry={one(geometry.box.h / 2 + 1)} />
        <g className="robot__lean"><g className="robot__body" transform={`rotate(${one(geometry.rot)} ${CENTER_X} ${one(geometry.cy)})`}>
          <Back geometry={geometry} skin={ids.skin} />
          <Skin geometry={geometry} ids={ids} picture={picture} />
          {size >= EMBLEM_MIN_PX && !picture ? <RoleEmblem role={role} geometry={geometry} /> : null}
          {face ? <Face geometry={geometry} ids={{ clip: ids.eyeClip, sclera: ids.sclera }} glyphs={big} /> : null}
        </g></g>
      </g></g></g>
      {star ? <Star /> : null}
    </svg>
  );
}
