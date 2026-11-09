import { useEffect, useId, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Avatar } from "./Avatar";
import { LENSBOT_SHAPES, LENSBOT_SHAPE_LABELS, lensbotShape } from "./robot/look";
import { ROBOT_COLORS } from "./robot/palette";
import type { AvatarOut, LensbotShape } from "../api/types";

// The eighteen Lensbot shapes and twelve colours (avatars v7). A pick changes one of them and drops any
// old badge (every bot has every tool) and keeps the role. Pressing on a tile and dragging across the
// others morphs the robot from one shape to the next: each tile under the pointer is a preview (`onPreview`, or `onChange`
// when the caller has no preview) and the one it is released on is the pick. A colour outside the
// twelve (a bot made before the robots) shows as its own swatch at the start of the row, so nothing
// looks unselected. It stays in the row for as long as the picker is open, so a move off it (a click,
// an arrow key) can be undone; its name says whether it is the bot's colour now.
export const CURRENT_COLOR_LABEL = "Current colour";
export const PREVIOUS_COLOR_LABEL = "Previous colour";
const TILE_ROBOT_PX = 32; // the tiles only blink: eighteen tracking robots in a card would be a crowd

const sameColor = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
const strayOf = (color: string): string | null => (ROBOT_COLORS.some(([swatch]) => sameColor(swatch, color)) ? null : color);
const isLensbot = (value: string | undefined): value is LensbotShape => (LENSBOT_SHAPES as readonly string[]).includes(value ?? "");

// The bot's colour from outside the palette, kept while the picker stays mounted.
function useStrayColor(color: string): string | null {
  const [stray, setStray] = useState(() => strayOf(color));
  const now = strayOf(color);
  if (now !== null && (stray === null || !sameColor(now, stray))) setStray(now);
  return stray;
}

export interface AvatarPickerProps {
  value: AvatarOut;
  onChange: (avatar: AvatarOut) => void;
  onPreview?: (avatar: AvatarOut | null) => void; // a drag's passing shapes; null when the drag ends
  compact?: boolean; // the look card's smaller tiles and dots
}

/** The shape tile under a pointer, if any. */
function tileAt(x: number, y: number): LensbotShape | null {
  const element = typeof document.elementFromPoint === "function" ? document.elementFromPoint(x, y) : null;
  const shape = element?.closest<HTMLElement>("[data-shape]")?.dataset.shape;
  return isLensbot(shape) ? shape : null;
}

// Press and drag across the tiles: every tile crossed is shown, the one released on is picked.
function useShapeDrag(value: AvatarOut, onChange: AvatarPickerProps["onChange"], onPreview: AvatarPickerProps["onPreview"]) {
  const drag = useRef<{ start: LensbotShape; shown: LensbotShape } | null>(null);
  const latest = useRef({ value, onChange, onPreview });
  latest.current = { value, onChange, onPreview };
  useEffect(() => {
    const end = () => {
      const state = drag.current;
      if (!state) return;
      drag.current = null;
      const { value: now, onChange: change, onPreview: preview } = latest.current;
      preview?.(null);
      // Released on the tile it started on: the click on that tile makes the pick.
      if (state.shown !== state.start) change({ ...now, shape: state.shown, badge: "none" });
    };
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    return () => { window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end); };
  }, []);
  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    const start = tileAt(event.clientX, event.clientY);
    if (start) drag.current = { start, shown: start };
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const state = drag.current;
    if (!state || (event.buttons & 1) === 0) return;
    const shape = tileAt(event.clientX, event.clientY);
    if (!shape || shape === state.shown) return;
    drag.current = { ...state, shown: shape };
    (onPreview ?? onChange)({ ...value, shape, badge: "none" });
  };
  return { onPointerDown, onPointerMove };
}

export function AvatarPicker({ value, onChange, onPreview, compact = false }: AvatarPickerProps) {
  const group = useId();
  const shape = lensbotShape(value.shape);
  const color = value.color.toLowerCase();
  const stray = useStrayColor(value.color);
  const strayIsCurrent = stray !== null && sameColor(stray, color);
  const strayLabel = strayIsCurrent ? CURRENT_COLOR_LABEL : PREVIOUS_COLOR_LABEL;
  const drag = useShapeDrag(value, onChange, onPreview);
  return (
    <div className={compact ? "avatar-picker avatar-picker--compact" : "avatar-picker"}>
      <fieldset className="avatar-picker__shapes" onPointerDown={drag.onPointerDown} onPointerMove={drag.onPointerMove}>
        <legend className="field__label">Shape</legend>
        {LENSBOT_SHAPES.map((lensbot) => (
          <label key={lensbot} className="avatar-picker__shape" data-shape={lensbot} title={LENSBOT_SHAPE_LABELS[lensbot]}>
            <input type="radio" name={`${group}-shape`} className="sr-only" aria-label={LENSBOT_SHAPE_LABELS[lensbot]}
              checked={shape === lensbot} onChange={() => onChange({ ...value, shape: lensbot, badge: "none" })} />
            <Avatar avatar={{ ...value, shape: lensbot, picture: null }} status="resting" size={TILE_ROBOT_PX} label={false} decorative />
          </label>
        ))}
      </fieldset>
      <fieldset className="avatar-picker__colors">
        <legend className="field__label">Colour</legend>
        {stray === null ? null : (
          <label className="avatar-picker__swatch" style={{ background: stray }} title={strayLabel}>
            <input type="radio" name={`${group}-color`} className="sr-only" aria-label={strayLabel}
              checked={strayIsCurrent} onChange={() => onChange({ ...value, color: stray, badge: "none" })} />
          </label>
        )}
        {ROBOT_COLORS.map(([swatch, label]) => (
          <label key={swatch} className="avatar-picker__swatch" style={{ background: swatch }} title={label}>
            <input type="radio" name={`${group}-color`} className="sr-only" aria-label={label}
              checked={color === swatch} onChange={() => onChange({ ...value, color: swatch, badge: "none" })} />
          </label>
        ))}
      </fieldset>
    </div>
  );
}
