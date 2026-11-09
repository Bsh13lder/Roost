// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  GROUND, LENSBOTS, POINT_COUNT, VIEW, blendGeometry, bodyPoints, lensGeometry, lensSpec, smoothPath, visorPieces,
} from "../src/components/robot/lensbot";
import { EYE_STYLES, EYE_STYLE_IDS } from "../src/components/robot/eyeStyles";

// The Lensbots (avatars v7, docs/design/robots-v7-sketch.html): eighteen soft bodies from one path
// function, every one 48 points, so any two morph; one dark visor holds two white eyes in one of
// seven eye styles.
const SHAPES = ["mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub",
  "sprout", "cheeky", "tower", "helmet", "bell", "puck", "pod"];

describe("the Lensbot shapes", () => {
  it("are eighteen, in the sketch's order, each with its own eye style and visor", () => {
    expect(LENSBOTS.map((spec) => spec.id)).toEqual(SHAPES);
    expect(LENSBOTS.map((spec) => spec.label)).toEqual(["Mochi", "Loaf", "Gumdrop", "Pebble", "Bun", "Acorn",
      "Marshmallow", "Dumpling", "Muffs", "Squish", "Cub", "Sprout", "Cheeky", "Tower", "Helmet", "Bell", "Puck", "Pod"]);
    expect(lensSpec("marsh")).toMatchObject({ eyes: "square", visor: "screen" });
    expect(lensSpec("pebble")).toMatchObject({ eyes: "ring", visor: "goggle" });
    expect(new Set(LENSBOTS.map((spec) => spec.eyes))).toEqual(new Set(EYE_STYLE_IDS)); // every eye style is some shape's own
    expect(new Set(LENSBOTS.map((spec) => spec.visor))).toEqual(new Set(["band", "pill", "goggle", "screen", "brow", "mask"]));
  });

  it("has seven eye styles: white, a dark pupil, sized in eye units", () => {
    expect(EYE_STYLE_IDS).toEqual(["round", "oval", "tall", "square", "half", "almond", "ring"]);
    for (const id of EYE_STYLE_IDS) {
      const style = EYE_STYLES[id];
      expect(style.d, id).toMatch(/^M.*Z$/);
      expect(style.hh, id).toBeCloseTo((style.bot - style.top) / 2);
      expect(style.pr, id).toBeLessThan(style.hw);
    }
    expect(EYE_STYLES.ring.ring).toBe(true);
  });

  it("every shape samples the same 48 points", () => {
    expect(POINT_COUNT).toBe(48);
    for (const spec of LENSBOTS) expect(bodyPoints(spec), spec.id).toHaveLength(POINT_COUNT);
  });

  it("stays inside the 48-unit view and stands on the ground", () => {
    for (const spec of LENSBOTS) {
      const { box } = lensGeometry(spec);
      expect(box.x0, spec.id).toBeGreaterThanOrEqual(0);
      expect(box.x1, spec.id).toBeLessThanOrEqual(VIEW);
      expect(box.y0, spec.id).toBeGreaterThanOrEqual(0);
      expect(box.y1, spec.id).toBeLessThanOrEqual(GROUND + 0.5);
    }
  });

  it("puts two eyes inside the visor, and the visor inside the body", () => {
    for (const spec of LENSBOTS) {
      const geometry = lensGeometry(spec);
      const { visor, eyes, box } = geometry;
      expect(eyes, spec.id).toHaveLength(2);
      expect(eyes.map((eye) => eye.side), spec.id).toEqual([-1, 1]);
      const style = EYE_STYLES[geometry.eyeStyle];
      for (const eye of eyes) {
        expect(eye.x - style.hw * eye.k, spec.id).toBeGreaterThan(visor.x - 2.5);
        expect(eye.x + style.hw * eye.k, spec.id).toBeLessThan(visor.x + visor.w + 2.5);
      }
      expect(visor.ey, spec.id).toBeGreaterThan(box.y0);
      expect(visor.ey, spec.id).toBeLessThan(box.y1);
      expect(geometry.eyeY, spec.id).toBe(visor.ey);
      expect(visorPieces(visor).length, spec.id).toBeGreaterThan(0);
      for (const piece of visorPieces(visor)) expect(piece, spec.id).toMatch(/^M.*Z$/);
    }
  });

  it("the goggle visor is two lenses and a bridge; the others are one piece", () => {
    expect(visorPieces(lensGeometry(lensSpec("pebble")).visor)).toHaveLength(3);
    expect(visorPieces(lensGeometry(lensSpec("mochi")).visor)).toHaveLength(1);
  });

  it("draws the ears, feet and nub its numbers ask for", () => {
    expect(lensGeometry(lensSpec("muffs")).ears.map((ear) => ear.kind)).toEqual(["side", "side"]);
    expect(lensGeometry(lensSpec("cub")).ears.map((ear) => ear.kind)).toEqual(["round", "round"]);
    expect(lensGeometry(lensSpec("bun")).feet).not.toBeNull();
    expect(lensGeometry(lensSpec("mochi")).feet).toBeNull();
    expect(lensGeometry(lensSpec("pod")).nub).not.toBeNull();
    expect(lensGeometry(lensSpec("pod")).rot).toBe(7);
  });

  it("a role can change the eye style and the visor; the geometry is computed once for each", () => {
    const own = lensGeometry(lensSpec("mochi"));
    const coded = lensGeometry(lensSpec("mochi"), { eyes: "square", visor: "screen" });
    expect(own.eyeStyle).toBe("round");
    expect(coded.eyeStyle).toBe("square");
    expect(coded.visor.kind).toBe("screen");
    expect(coded.d).toBe(own.d); // the body stays its own
    expect(lensGeometry(lensSpec("mochi"))).toBe(own);
    expect(lensGeometry(lensSpec("mochi"), { eyes: "square", visor: "screen" })).toBe(coded);
  });

  it("a shape it has never heard of is the Mochi", () => {
    expect(lensSpec("hexagon" as never).id).toBe("mochi");
  });

  it("blends two bodies point by point for the morph, and ends on the second", () => {
    const a = lensGeometry(lensSpec("tower"));
    const b = lensGeometry(lensSpec("squish"));
    const half = blendGeometry(a, b, 0.5);
    expect(half.pts).toHaveLength(POINT_COUNT);
    expect(half.pts[0][0]).toBeCloseTo((a.pts[0][0] + b.pts[0][0]) / 2);
    expect(half.box.w).toBeCloseTo((a.box.w + b.box.w) / 2);
    expect(half.d).toBe(smoothPath(half.pts));
    expect(blendGeometry(a, b, 1)).toBe(b);
  });

  it("writes a closed cubic path with at most two decimals per number", () => {
    const d = smoothPath([[0, 0], [10, 0], [10, 10], [0, 10]]);
    expect(d.startsWith("M0 0C")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    expect(d).not.toMatch(/\d\.\d\d\d/);
  });
});
