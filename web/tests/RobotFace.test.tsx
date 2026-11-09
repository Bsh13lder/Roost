import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { RobotFace } from "../src/components/robot/RobotFace";
import { LENSBOTS, lensGeometry, lensSpec } from "../src/components/robot/lensbot";
import { EYE_STYLES, EYE_STYLE_IDS } from "../src/components/robot/eyeStyles";
import { BOT_ROLES } from "../src/components/robot/look";
import { EMBLEM_MIN_PX } from "../src/components/robot/emblem";
import { EVENT_MS, MOMENT_FACE, MOMENT_GLYPH, ROBOT_MOMENTS } from "../src/components/robot/moments";
import { LIVE_OVER_PX, resetLookAtForTests } from "../src/components/robot/lookAt";
import { installObserverStub, type ObserverStub } from "./lookAtStub";

let observer: ObserverStub;
beforeEach(() => { resetLookAtForTests(); observer = installObserverStub(); });
afterEach(() => { cleanup(); observer.restore(); vi.useRealTimers(); });

const ONE_EYE_GLYPHS = ["q", "bang", "env", "chk", "hand"];
const BOTH_EYE_GLYPHS = ["scan", "dots"];

describe("RobotFace (a Lensbot)", () => {
  it("draws every shape: a body, a shadow, a dark visor and two white eyes with a pupil, two highlights and two lids, no mouth", () => {
    for (const spec of LENSBOTS) {
      const { container, unmount } = render(<RobotFace shape={spec.id} color="#3b82f6" />);
      const svg = container.querySelector("svg.robot");
      expect(svg?.getAttribute("data-shape"), spec.id).toBe(spec.id);
      expect(svg?.getAttribute("data-eyes"), spec.id).toBe(spec.eyes);
      expect(svg?.getAttribute("viewBox")).toBe("0 0 48 48");
      expect(svg?.querySelector("path.robot__skin")?.getAttribute("d"), spec.id).toMatch(/^M.*Z$/);
      expect(svg?.querySelector(".robot__shadow"), spec.id).not.toBeNull();
      expect(svg?.querySelectorAll(".robot__visor").length, spec.id).toBeGreaterThan(0);
      expect(svg?.querySelector(".robot__mouth"), spec.id).toBeNull();
      const eyes = svg?.querySelectorAll(".robot__eye") ?? [];
      expect(eyes, spec.id).toHaveLength(2);
      for (const eye of eyes) {
        expect(eye.querySelector(".robot__lens .robot__sclera")?.getAttribute("d"), spec.id).toBe(EYE_STYLES[spec.eyes].d);
        expect(eye.querySelector(".robot__pupil .robot__pupil-dot"), spec.id).not.toBeNull();
        expect(eye.querySelectorAll(".robot__pupil .robot__hl"), spec.id).toHaveLength(2);
        expect(eye.querySelectorAll(".robot__lid"), spec.id).toHaveLength(2);
      }
      expect(eyes[0]).toHaveClass("robot__eye--l");
      expect(eyes[1]).toHaveClass("robot__eye--r");
      unmount();
    }
  });

  it("draws each of the seven eye styles, the ring lens with its ring", () => {
    for (const id of EYE_STYLE_IDS) {
      const spec = LENSBOTS.find((one) => one.eyes === id)!;
      const { container, unmount } = render(<RobotFace shape={spec.id} color="#14b8a6" size={64} />);
      expect(container.querySelector("svg.robot")?.getAttribute("data-eyes")).toBe(id);
      expect(container.querySelectorAll(".robot__eye-ring").length > 0, id).toBe(id === "ring");
      unmount();
    }
  });

  it("draws the ears, the feet and the nub behind the body", () => {
    const muffs = render(<RobotFace shape="muffs" color="#3b82f6" />);
    expect(muffs.container.querySelectorAll(".robot__ear")).toHaveLength(2);
    muffs.unmount();
    const bun = render(<RobotFace shape="bun" color="#3b82f6" />);
    expect(bun.container.querySelectorAll(".robot__foot")).toHaveLength(2);
    bun.unmount();
    const pod = render(<RobotFace shape="pod" color="#3b82f6" />);
    expect(pod.container.querySelector(".robot__nub")).not.toBeNull();
  });

  it("carries its colour and its look as CSS variables", () => {
    const { container } = render(<RobotFace shape="marsh" color="#3b82f6" size={64} />);
    const style = container.querySelector("svg.robot")?.getAttribute("style") ?? "";
    expect(style).toMatch(/--bot: ?#3b82f6/);
    expect(style).toMatch(/--bot-light: ?rgb\(/);
    expect(style).toMatch(/--oy: ?[\d.]+px/);
    expect(style).toMatch(/--blink-dur: ?[\d.]+s/);
  });

  it.each(ROBOT_MOMENTS)("the %s status sets the posture, the lids and the glyph in the eyes", (moment) => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" moment={moment} size={64} />);
    const svg = container.querySelector("svg.robot");
    expect(svg?.getAttribute("data-moment")).toBe(moment);
    expect(svg?.getAttribute("data-face")).toBe(MOMENT_FACE[moment]);
    expect(svg?.getAttribute("data-g")).toBe(MOMENT_GLYPH[moment]);
  });

  it("maps the statuses to the sketch's lids and glyphs", () => {
    expect(MOMENT_FACE).toEqual({ rest: "open", onit: "open", ask: "wide", stuck: "sad", off: "closed" });
    expect(MOMENT_GLYPH).toEqual({ rest: "", onit: "onit", ask: "ask", stuck: "stuck", off: "off" });
  });

  it("pre-draws the glyphs in the eye field: a scan bar and dots in both eyes, ? ! envelope check cursor in the right, and the z's", () => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} />);
    const [left, right] = container.querySelectorAll(".robot__eye");
    for (const glyph of BOTH_EYE_GLYPHS) {
      expect(left.querySelector(`.robot__g--${glyph}`), glyph).not.toBeNull();
      expect(right.querySelector(`.robot__g--${glyph}`), glyph).not.toBeNull();
    }
    for (const glyph of ONE_EYE_GLYPHS) {
      expect(right.querySelector(`.robot__g--${glyph}`), glyph).not.toBeNull();
      expect(left.querySelector(`.robot__g--${glyph}`), glyph).toBeNull();
    }
    expect(container.querySelector(".robot__zz")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("draws no glyphs at 32 px or less: only the shape, the colour and blinking eyes", () => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={32} moment="ask" />);
    expect(container.querySelector(".robot__g")).toBeNull();
    expect(container.querySelector(".robot__zz")).toBeNull();
    expect(container.querySelectorAll(".robot__eye")).toHaveLength(2);
  });

  it("is live above 32 px and only blinks at 32 px or less", () => {
    expect(LIVE_OVER_PX).toBe(32);
    const small = render(<RobotFace shape="mochi" color="#3b82f6" size={32} />);
    const smallSvg = small.container.querySelector("svg.robot");
    expect(smallSvg).toHaveClass("robot--xs");
    expect(smallSvg).not.toHaveClass("robot--live");
    expect(observer.observed).toHaveLength(0);
    small.unmount();
    const big = render(<RobotFace shape="mochi" color="#3b82f6" size={33} />);
    const bigSvg = big.container.querySelector("svg.robot");
    expect(bigSvg).toHaveClass("robot--live");
    expect(observer.observed).toHaveLength(1);
    expect(observer.observed[0]).toBe(bigSvg);
    big.unmount();
    expect(observer.observed).toHaveLength(0);
  });

  it("does not track the pointer when still (reduced motion), and still shows its glyph", () => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={96} moment="ask" still />);
    expect(container.querySelector("svg.robot")).toHaveClass("robot--still");
    expect(container.querySelector(".robot__g--q")).not.toBeNull();
    expect(observer.observed).toHaveLength(0);
  });

  it("plays an event once, as a class for its length, with the event's lids and glyph", () => {
    vi.useFakeTimers();
    const { container, rerender } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} event={{ name: "created", key: 1 }} />);
    const svg = container.querySelector("svg.robot");
    expect(svg).toHaveClass("robot--ev-created");
    expect(svg?.getAttribute("data-face")).toBe("wide");
    act(() => { vi.advanceTimersByTime(EVENT_MS.created + 1); });
    expect(svg).not.toHaveClass("robot--ev-created");
    expect(svg?.getAttribute("data-face")).toBe("open");
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} event={{ name: "created", key: 1 }} />);
    expect(svg).not.toHaveClass("robot--ev-created");
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} event={{ name: "done", key: 2 }} />);
    expect(svg).toHaveClass("robot--ev-done");
    expect(svg?.getAttribute("data-face")).toBe("happy");
    expect(svg?.getAttribute("data-g")).toBe("done");
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} event={{ name: "msg", key: 3 }} />);
    expect(svg?.getAttribute("data-g")).toBe("msg");
  });

  it("thinks for as long as it is told: focused lids and three dots across both eyes", () => {
    const { container, rerender } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} moment="onit" thinking />);
    const svg = container.querySelector("svg.robot");
    expect(svg).toHaveClass("robot--ev-think");
    expect(svg?.getAttribute("data-face")).toBe("focus");
    expect(svg?.getAttribute("data-g")).toBe("think");
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} moment="onit" />);
    expect(svg).not.toHaveClass("robot--ev-think");
    expect(svg?.getAttribute("data-face")).toBe("open");
    expect(svg?.getAttribute("data-g")).toBe("onit");
  });

  it("waits for you to take control with a hand in its eye", () => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} moment="stuck" control />);
    expect(container.querySelector("svg.robot")?.getAttribute("data-g")).toBe("ctrl");
  });

  it("squishes when clicked, only when asked to, and is never a focus stop of its own", () => {
    vi.useFakeTimers();
    const plain = render(<RobotFace shape="mochi" color="#3b82f6" size={64} />);
    const plainSvg = plain.container.querySelector("svg.robot")!;
    fireEvent.click(plainSvg);
    expect(plainSvg).not.toHaveClass("robot--poked");
    plain.unmount();
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} poke />);
    const svg = container.querySelector("svg.robot")!;
    expect(svg.getAttribute("tabindex")).toBeNull(); // it sits inside a button or a link
    fireEvent.click(svg);
    expect(svg).toHaveClass("robot--poked");
    expect(svg.getAttribute("data-face")).toBe("wide");
    act(() => { vi.advanceTimersByTime(EVENT_MS.poke + 1); });
    expect(svg).not.toHaveClass("robot--poked");
    expect(svg.getAttribute("data-face")).toBe("open");
  });

  it("wears the star only when asked", () => {
    const { container, rerender } = render(<RobotFace shape="mochi" color="#8b5cf6" />);
    expect(container.querySelector(".robot__star")).toBeNull();
    rerender(<RobotFace shape="mochi" color="#8b5cf6" star />);
    expect(container.querySelector(".robot__star .robot__star-mark")).not.toBeNull();
  });

  it("shows the bot's own picture inside the body, with no eyes unless asked", () => {
    const { container, rerender } = render(<RobotFace shape="bell" color="#3b82f6" size={64} picture="/api/bots/b1/picture?v=0123456789ab" />);
    const svg = container.querySelector("svg.robot")!;
    const picture = svg.querySelector("image.robot__picture");
    expect(picture?.getAttribute("href")).toBe("/api/bots/b1/picture?v=0123456789ab");
    const clip = picture?.getAttribute("clip-path") ?? "";
    expect(clip).toMatch(/^url\(#robot-clip-/);
    expect(svg.querySelector(`clipPath[id="${clip.slice(5, -1)}"] path`)?.getAttribute("d")).toMatch(/^M.*Z$/);
    expect(svg.querySelectorAll(".robot__eye")).toHaveLength(0);
    expect(svg.querySelector(".robot__visor")).toBeNull();
    expect(svg).not.toHaveClass("robot--live"); // nothing to track with
    rerender(<RobotFace shape="bell" color="#3b82f6" size={64} picture="/p" pictureEyes />);
    expect(svg.querySelectorAll(".robot__eye")).toHaveLength(2);
    expect(svg.querySelectorAll(".robot__visor").length).toBeGreaterThan(0);
    expect(svg).toHaveClass("robot--live");
  });

  it("is an image with a name when titled, and hidden when not", () => {
    const { rerender } = render(<RobotFace shape="helmet" color="#8b5cf6" title="On it" />);
    expect(screen.getByRole("img", { name: "On it" })).toBeInTheDocument();
    rerender(<RobotFace shape="helmet" color="#8b5cf6" />);
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("morphs when its shape changes: the body tweens to the new path", () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    const { container, rerender } = render(<RobotFace shape="tower" color="#3b82f6" size={96} />);
    const svg = container.querySelector("svg.robot")!;
    const before = svg.querySelector("path.robot__skin")!.getAttribute("d");
    expect(svg.getAttribute("data-ey")).toBe(String(lensGeometry(lensSpec("tower")).eyeY.toFixed(2)).replace(/\.?0+$/, ""));
    frames.length = 0; // the pointer loop's own frame, asked for when the robot registered
    rerender(<RobotFace shape="squish" color="#3b82f6" size={96} />);
    act(() => { frames.shift()!(0); });
    act(() => { frames.shift()!(200); });
    expect(svg).toHaveClass("robot--morph");
    const during = svg.querySelector("path.robot__skin")!.getAttribute("d");
    expect(during).not.toBe(before);
    act(() => { frames.shift()!(2000); });
    expect(svg).not.toHaveClass("robot--morph");
    const after = svg.querySelector("path.robot__skin")!.getAttribute("d");
    expect(after).not.toBe(during);
    expect(svg.getAttribute("data-shape")).toBe("squish");
    vi.unstubAllGlobals();
  });
});

describe("RobotFace role looks", () => {
  it.each(BOT_ROLES.filter((role) => role !== "general"))("a %s bot wears its emblem on its body", (role) => {
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} role={role} />);
    const svg = container.querySelector("svg.robot");
    expect(svg?.getAttribute("data-role")).toBe(role);
    const emblems = svg?.querySelectorAll(".robot__emblem") ?? [];
    expect(emblems).toHaveLength(1);
    expect(emblems[0]).toHaveClass(`robot__emblem--${role}`);
    expect(emblems[0].querySelectorAll(".robot__emblem-plate, .robot__emblem-mark").length).toBeGreaterThan(0);
  });

  it("a general bot, or one with no role, wears no emblem", () => {
    const { container, rerender } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} role="general" />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
    expect(container.querySelector("svg.robot")?.getAttribute("data-role")).toBe("general");
  });

  it.each(BOT_ROLES)("hides the %s emblem at 24 px: only the shape and the colour remain", (role) => {
    expect(EMBLEM_MIN_PX).toBe(32);
    const { container } = render(<RobotFace shape="mochi" color="#3b82f6" size={24} role={role} />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
    expect(container.querySelector("path.robot__skin")).not.toBeNull();
  });

  it("shows the emblem from 32 px up, in every shape", () => {
    for (const spec of LENSBOTS) {
      const { container, unmount } = render(<RobotFace shape={spec.id} color="#3b82f6" size={EMBLEM_MIN_PX} role="tasks" />);
      expect(container.querySelector(".robot__emblem--tasks"), spec.id).not.toBeNull();
      unmount();
    }
  });

  it("code squares the frame and the eyes; a picture hides the emblem", () => {
    const { container, rerender } = render(<RobotFace shape="mochi" color="#3b82f6" size={64} role="code" />);
    const svg = container.querySelector("svg.robot");
    expect(svg?.getAttribute("data-eyes")).toBe("square");
    expect(svg?.getAttribute("data-visor")).toBe("screen");
    rerender(<RobotFace shape="mochi" color="#3b82f6" size={64} role="code" picture="/p" />);
    expect(container.querySelector(".robot__emblem")).toBeNull();
  });
});
