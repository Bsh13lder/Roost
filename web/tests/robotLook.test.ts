import { describe, expect, it } from "vitest";
import {
  AVATAR_SHAPES, BOT_ROLES, DEFAULT_LENSBOT_SHAPE, LEGACY_SHAPE_TO_LENSBOT, LENSBOT_SHAPES, LENSBOT_SHAPE_LABELS,
  ROBOT_SIGNAL_STYLE, ROLE_LABELS, botRole, lensbotShape, lookOf, robotScreen,
} from "../src/components/robot/look";
import { ROLE_LOOKS, suggestRole } from "../src/components/robot/roles";
import { BOT_DEFAULT_COLORS, ROBOT_COLORS, nextBotColor, shade, surpriseLook, tint } from "../src/components/robot/palette";

describe("the robot look (Lensbots)", () => {
  it("draws a Lensbot as itself and every old shape through the one table", () => {
    for (const shape of LENSBOT_SHAPES) expect(lensbotShape(shape)).toBe(shape);
    // The ten ghosts (v5)...
    expect(lensbotShape("dome")).toBe("mochi");
    expect(lensbotShape("tall")).toBe("marsh");
    expect(lensbotShape("wide")).toBe("squish");
    expect(lensbotShape("round")).toBe("bun");
    expect(lensbotShape("hooded")).toBe("bell");
    // ...the six Boxbot heads (V1), through the ghost they drew as...
    expect(lensbotShape("classic")).toBe("mochi");
    expect(lensbotShape("soft")).toBe("bun");
    expect(lensbotShape("cube")).toBe("helmet");
    expect(lensbotShape("monitor")).toBe("bell");
    // ...and the S1.6 birds.
    expect(lensbotShape("egg")).toBe("cub");
    expect(lensbotShape("pear")).toBe("gumdrop");
    expect(lensbotShape("plump")).toBe("pebble");
    expect(lensbotShape("crest")).toBe("acorn");
    expect(Object.keys(LEGACY_SHAPE_TO_LENSBOT)).toEqual([
      "dome", "tall", "wide", "round", "droopy", "spire", "comet", "cape", "puff", "hooded",
      "classic", "soft", "cube", "monitor", "egg", "pear", "plump", "crest"]);
    for (const shape of AVATAR_SHAPES) expect(LENSBOT_SHAPES, shape).toContain(lensbotShape(shape));
  });

  it("lists every accepted shape once: the eighteen Lensbots first, then the old names", () => {
    expect(AVATAR_SHAPES.slice(0, 18)).toEqual(LENSBOT_SHAPES);
    expect(new Set(AVATAR_SHAPES).size).toBe(AVATAR_SHAPES.length);
    expect(AVATAR_SHAPES).toHaveLength(36);
    expect(LENSBOT_SHAPE_LABELS.marsh).toBe("Marshmallow");
    expect(DEFAULT_LENSBOT_SHAPE).toBe("mochi");
  });

  it("a shape it has never heard of (a newer server) draws the Mochi, not a blank", () => {
    expect(lensbotShape("hexagon")).toBe("mochi");
  });

  it("still reads a stored screen style: accepted on the wire, no longer drawn", () => {
    expect(robotScreen(undefined)).toBe(ROBOT_SIGNAL_STYLE);
    expect(robotScreen("neon")).toBe(ROBOT_SIGNAL_STYLE);
    expect(robotScreen("pixel")).toBe("pixel");
  });

  it("a look to save never carries the picture or an old badge, keeps the stored screen, and carries a role it has", () => {
    expect(lookOf({ shape: "soft", color: "#14b8a6", badge: "tasks", picture: "/p" })).toEqual(
      { shape: "soft", color: "#14b8a6", badge: "none", screen: "glow" });
    expect(lookOf({ shape: "puff", color: "#14b8a6", badge: "none", screen: "pixel" }).screen).toBe("pixel");
    expect(lookOf({ shape: "pod", color: "#14b8a6", badge: "none", role: "seo" })).toEqual(
      { shape: "pod", color: "#14b8a6", badge: "none", screen: "glow", role: "seo" });
    expect(lookOf({ shape: "pod", color: "#14b8a6", badge: "none", role: null })).not.toHaveProperty("role");
  });
});

describe("the role looks", () => {
  it("are eight, and an avatar without one (or with one it does not know) counts as general", () => {
    expect(BOT_ROLES).toEqual(["general", "tasks", "code", "seo", "money", "social", "research", "writer"]);
    expect(ROLE_LABELS.seo).toBe("SEO");
    expect(botRole(undefined)).toBe("general");
    expect(botRole(null)).toBe("general");
    expect(botRole("hacker")).toBe("general");
    expect(botRole("writer")).toBe("writer");
  });

  it("code nudges the frame square and the eyes soft-square; general changes nothing", () => {
    expect(ROLE_LOOKS.code).toEqual({ eyes: "square", visor: "screen" });
    expect(ROLE_LOOKS.general).toEqual({});
  });

  it.each([
    ["Keeps my tasks in order", "tasks"],
    ["Plans the to-do list", "tasks"],
    ["Improves HiMap's SEO", "seo"],
    ["Writes code for the app", "code"],
    ["Full-stack dev helper", "code"],
    ["Tracks money and the budget", "money"],
    ["Watches the monthly budget", "money"],
    ["Runs our social posts", "social"],
    ["Posts to Instagram daily", "social"],
    ["Does market research", "research"],
    ["Helps me write blog posts", "writer"],
    ["A writer for the newsletter", "writer"],
  ])("suggests a role from the job %j: %s", (job, role) => {
    expect(suggestRole(job)).toBe(role);
  });

  it("suggests nothing when no keyword fits, and never reads a word inside another", () => {
    expect(suggestRole("Finds things on the web")).toBeNull();
    expect(suggestRole("")).toBeNull();
    expect(suggestRole("Checks every device")).toBeNull(); // "dev" only as a word of its own
    expect(suggestRole("Codenames for products")).toBeNull();
  });
});

describe("the robot palette", () => {
  it("a new bot takes the first colour nobody wears, in any case", () => {
    expect(nextBotColor([])).toBe("#8b5cf6");
    expect(nextBotColor(["#8B5CF6", "#22c55e"])).toBe("#3b82f6");
  });

  it("once every default colour is worn, they come round again", () => {
    expect(nextBotColor([...BOT_DEFAULT_COLORS])).toBe(BOT_DEFAULT_COLORS[0]);
    expect(nextBotColor([...BOT_DEFAULT_COLORS, "#ffffff"])).toBe(BOT_DEFAULT_COLORS[1]);
  });

  it("tints toward white and shades toward black", () => {
    expect(tint("#000000", 0.5)).toBe("rgb(128, 128, 128)");
    expect(tint("#3b82f6", 0)).toBe("rgb(59, 130, 246)");
    expect(shade("#ffffff", 0.7)).toBe("rgb(179, 179, 179)");
  });

  it("Surprise me always changes the shape and the colour", () => {
    const now = { shape: "mochi" as const, color: ROBOT_COLORS[0][0] };
    for (const roll of [0, 0.3, 0.99]) {
      const next = surpriseLook(now, () => roll);
      expect(next.shape).not.toBe(now.shape);
      expect(LENSBOT_SHAPES).toContain(next.shape);
      expect(next.color).not.toBe(now.color);
      expect(ROBOT_COLORS.map(([color]) => color)).toContain(next.color);
    }
  });
});
