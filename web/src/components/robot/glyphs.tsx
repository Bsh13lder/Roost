import type { EyeStyle } from "./eyeStyles";

// The glyphs in the eye field (avatars v7 "info in the eyes"), drawn in eye units and centred on the
// eye's middle. Every one is pre-drawn and hidden; robot.css shows the one data-g names. Both eyes hold
// the On it scan bar and the thinking dots; the right eye holds the one-eye glyphs: "?" (Asking you),
// "!" (Stuck), an envelope (New message), a check (Done) and a raised hand (waiting for you to Take control, C3).
const DOT_X = [-4.9, 0, 4.9] as const;

function BothEyes() {
  return (
    <>
      <g className="robot__g robot__g--scan">
        <rect className="robot__scan-bar robot__ink-fill" x="-1.5" y="-7.6" width="3" height="15.2" rx="1.5" />
      </g>
      <g className="robot__g robot__g--dots">
        {DOT_X.map((x, index) => <circle key={x} className={`robot__dot robot__dot--${index} robot__ink-fill`} cx={x} r="2" />)}
      </g>
    </>
  );
}

function RightEye() {
  return (
    <>
      <g className="robot__g robot__g--q">
        <path className="robot__ink-line" d="M-3.5 -3.7C-3.5 -7.8 3.7 -7.8 3.7 -3.5C3.7 -.6 0 -.5 0 2.3" strokeWidth="2.8" />
        <circle className="robot__ink-fill" cy="6.3" r="1.7" />
      </g>
      <g className="robot__g robot__g--bang">
        <path className="robot__ink-line" d="M0 -7V2" strokeWidth="3.1" />
        <circle className="robot__ink-fill" cy="6.3" r="1.8" />
      </g>
      <g className="robot__g robot__g--env">
        <rect className="robot__ink-line" x="-6" y="-4.3" width="12" height="8.6" rx="1.6" strokeWidth="1.9" />
        <path className="robot__ink-line" d="M-5.2 -3.3L0 1L5.2 -3.3" strokeWidth="1.9" />
      </g>
      <g className="robot__g robot__g--chk">
        <path className="robot__check robot__ink-line" d="M-5.4 .2L-1.7 3.9L5.4 -4" strokeWidth="3" pathLength={1} strokeDasharray="1 1" />
      </g>
      <g className="robot__g robot__g--hand">
        <path className="robot__hand robot__ink-fill"
          d="M-4.6 -0.4V-4.6A1.05 1.05 0 0 1 -2.5 -4.6V-1.2V-6.2A1.05 1.05 0 0 1 -0.4 -6.2V-1.2V-6.6A1.05 1.05 0 0 1 1.7 -6.6V-1.2V-5.4A1.05 1.05 0 0 1 3.8 -5.4V0.6L5 -1.2A1.1 1.1 0 0 1 6.8 0L4.4 4.6C3.5 6.3 2 7.2 0 7.2C-2.8 7.2 -4.6 5.4 -4.6 2.6Z" />
      </g>
    </>
  );
}

export function Glyphs({ style, side }: { style: EyeStyle; side: -1 | 1 }) {
  return (
    <g className="robot__glyphs" transform={`translate(0 ${style.mid}) scale(${style.gs})`} aria-hidden="true">
      <BothEyes />
      {side > 0 ? <RightEye /> : null}
    </g>
  );
}

const Z_PATH = "M-2.6 -2.6H2.6L-2.6 2.6H2.6";

/** The Off duty z's, drifting up beside the right eye. */
export function Zeds({ x, y }: { x: number; y: number }) {
  return (
    <g className="robot__zz" transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})`} aria-hidden="true">
      <g className="robot__zf">
        <path className="robot__z" d={Z_PATH} strokeWidth="1.25" />
        <path className="robot__z robot__z--small" d={Z_PATH} transform="translate(4.4 -4) scale(.6)" strokeWidth="1.6" />
      </g>
    </g>
  );
}
