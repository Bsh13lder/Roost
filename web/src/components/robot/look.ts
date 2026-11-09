// How a bot looks (avatars v7, the Lensbots): eighteen shapes, the one table that draws an old stored
// shape as a Lensbot, and the eight roles a body can wear. Stored avatars keep their old value; nothing
// migrates. roost/constants.py holds the same lists of shapes and roles, and tests/test_bot_look.py
// checks that they match and that every shape the gateway accepts has a Lensbot here.
import type { AvatarOut, AvatarShape, BotRole, LegacyAvatarShape, LensbotShape, RobotScreen } from "../../api/types";

export const LENSBOT_SHAPES: readonly LensbotShape[] = [
  "mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub", "sprout",
  "cheeky", "tower", "helmet", "bell", "puck", "pod",
];
export const LENSBOT_SHAPE_LABELS: Readonly<Record<LensbotShape, string>> = {
  mochi: "Mochi", loaf: "Loaf", gumdrop: "Gumdrop", pebble: "Pebble", bun: "Bun", acorn: "Acorn", marsh: "Marshmallow",
  dumpling: "Dumpling", muffs: "Muffs", squish: "Squish", cub: "Cub", sprout: "Sprout", cheeky: "Cheeky", tower: "Tower",
  helmet: "Helmet", bell: "Bell", puck: "Puck", pod: "Pod",
};
export const DEFAULT_LENSBOT_SHAPE: LensbotShape = "mochi";

// Every old saved shape, in roost/constants.py AVATAR_SHAPES order: the ten ghosts (v5), then the Boxbot
// heads (V1) and the S1.6 birds through the ghost each drew as. One entry per line: tests/test_bot_look.py
// reads this table.
export const LEGACY_SHAPE_TO_LENSBOT: Readonly<Record<LegacyAvatarShape, LensbotShape>> = {
  dome: "mochi",
  tall: "marsh",
  wide: "squish",
  round: "bun",
  droopy: "gumdrop",
  spire: "acorn",
  comet: "pebble",
  cape: "helmet",
  puff: "cub",
  hooded: "bell",
  classic: "mochi",
  soft: "bun",
  cube: "helmet",
  monitor: "bell",
  egg: "cub",
  pear: "gumdrop",
  plump: "pebble",
  crest: "acorn",
};
export const AVATAR_SHAPES: readonly AvatarShape[] = [
  ...LENSBOT_SHAPES, ...(Object.keys(LEGACY_SHAPE_TO_LENSBOT) as LegacyAvatarShape[]),
];

// The roles (avatars v7 role looks), in roost/constants.py BOT_ROLES order. General wears no emblem.
export const BOT_ROLES: readonly BotRole[] = ["general", "tasks", "code", "seo", "money", "social", "research", "writer"];
export const ROLE_LABELS: Readonly<Record<BotRole, string>> = {
  general: "General", tasks: "Tasks", code: "Code", seo: "SEO", money: "Money", social: "Social", research: "Research",
  writer: "Writer",
};
export const DEFAULT_ROLE: BotRole = "general";

// The screen style of a Boxbot (V1). Still on the wire, in template files and in stored avatars, so it
// is still read and carried; a Lensbot has no screen, so nothing draws it any more.
export const ROBOT_SCREENS: readonly RobotScreen[] = ["glow", "pixel", "signal"];
export const ROBOT_SIGNAL_STYLE: RobotScreen = "glow";

const isLensbot = (shape: string): shape is LensbotShape => (LENSBOT_SHAPES as readonly string[]).includes(shape);

/** The Lensbot a stored shape draws: a Lensbot is itself, an old shape maps, anything else is the Mochi. */
export function lensbotShape(shape: string): LensbotShape {
  if (isLensbot(shape)) return shape;
  return LEGACY_SHAPE_TO_LENSBOT[shape as LegacyAvatarShape] ?? DEFAULT_LENSBOT_SHAPE;
}

/** The role a stored avatar wears: none, or one this web does not know, is general. */
export function botRole(role: string | null | undefined): BotRole {
  return (BOT_ROLES as readonly string[]).includes(role ?? "") ? (role as BotRole) : DEFAULT_ROLE;
}

export function robotScreen(screen: string | null | undefined): RobotScreen {
  return (ROBOT_SCREENS as readonly string[]).includes(screen ?? "") ? (screen as RobotScreen) : ROBOT_SIGNAL_STYLE;
}

// What a look editor sends: the shape, colour and role (and the stored screen, unchanged), never the picture's address.
export type AvatarLook = Pick<AvatarOut, "shape" | "color" | "badge" | "screen" | "role">;

export function lookOf(avatar: AvatarOut): AvatarLook {
  const look: AvatarLook = { shape: avatar.shape, color: avatar.color, badge: "none", screen: robotScreen(avatar.screen) };
  return avatar.role ? { ...look, role: avatar.role } : look;
}
