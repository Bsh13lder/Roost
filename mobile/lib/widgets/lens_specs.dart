// The eighteen Lensbot bodies as rows of numbers, ported from
// web/src/components/robot/lensbot.ts (LENSBOTS) and look.ts (shape tables).

enum VisorKind { band, pill, goggle, screen, brow, mask }

enum EyeId { round, oval, tall, square, half, almond, ring }

class LensSpec {
  const LensSpec(
    this.id,
    this.label,
    this.w,
    this.h,
    this.nt,
    this.nb,
    this.eyes,
    this.visor, {
    this.taper = 0,
    this.rot = 0,
    this.dents = const [],
    this.ears,
    this.feet = false,
    this.nub,
    this.vh,
  });

  final String id;
  final String label;
  final double w, h, nt, nb, taper, rot;
  final List<(double, double, double)> dents; // angle, depth, width
  final (double, double, bool)? ears; // angle, radius, side (true) or round
  final bool feet;
  final double? nub;
  final double? vh;
  final EyeId eyes;
  final VisorKind visor;
}

const lensSpecs = <LensSpec>[
  LensSpec('mochi', 'Mochi', 38, 30, 2.2, 3.4, EyeId.round, VisorKind.band, taper: 0.06),
  LensSpec('loaf', 'Loaf', 40, 27, 2.1, 4.4, EyeId.oval, VisorKind.band),
  LensSpec('gumdrop', 'Gumdrop', 35, 34, 1.8, 3.4, EyeId.tall, VisorKind.pill, taper: 0.22),
  LensSpec('pebble', 'Pebble', 38, 30, 2.3, 2.3, EyeId.ring, VisorKind.goggle, rot: -4),
  LensSpec('bun', 'Bun', 37, 30, 2, 2.8, EyeId.half, VisorKind.band, dents: [(-90, 0.07, 26)], feet: true),
  LensSpec('acorn', 'Acorn', 34, 35, 2.6, 1.9, EyeId.almond, VisorKind.brow, taper: -0.16),
  LensSpec('marsh', 'Marshmallow', 31, 36, 3.3, 3.3, EyeId.square, VisorKind.screen),
  LensSpec('dumpling', 'Dumpling', 42, 28, 1.7, 3.6, EyeId.half, VisorKind.mask, taper: 0.15),
  LensSpec('muffs', 'Muffs', 33, 32, 2.4, 2.8, EyeId.oval, VisorKind.pill, ears: (90, 4.6, true)),
  LensSpec('squish', 'Squish', 43, 24, 2.6, 2.8, EyeId.almond, VisorKind.band, vh: 14),
  LensSpec('cub', 'Cub', 36, 30, 2.3, 2.6, EyeId.round, VisorKind.goggle, ears: (42, 5, false)),
  LensSpec('sprout', 'Sprout', 34, 31, 2.2, 3, EyeId.tall, VisorKind.pill,
      dents: [(-62, -0.1, 11), (-118, -0.1, 11)]),
  LensSpec('cheeky', 'Cheeky', 40, 30, 2, 2.4, EyeId.round, VisorKind.band,
      dents: [(25, -0.07, 28), (155, -0.07, 28)]),
  LensSpec('tower', 'Tower', 28, 33, 2.6, 3.6, EyeId.square, VisorKind.screen, feet: true),
  LensSpec('helmet', 'Helmet', 38, 31, 1.9, 7, EyeId.half, VisorKind.mask),
  LensSpec('bell', 'Bell', 35, 33, 2, 5, EyeId.almond, VisorKind.brow, taper: 0.3),
  LensSpec('puck', 'Puck', 42, 22, 3.6, 3.6, EyeId.oval, VisorKind.band, feet: true, vh: 14.5),
  LensSpec('pod', 'Pod', 34, 32, 2.4, 2.4, EyeId.ring, VisorKind.goggle, rot: 7, nub: 2.4),
];

const lensbotShapes = [
  'mochi', 'loaf', 'gumdrop', 'pebble', 'bun', 'acorn', 'marsh', 'dumpling', //
  'muffs', 'squish', 'cub', 'sprout', 'cheeky', 'tower', 'helmet', 'bell',
  'puck', 'pod',
];

/// Older stored shapes draw as a Lensbot (look.ts LEGACY_SHAPE_TO_LENSBOT).
const legacyShapeToLensbot = <String, String>{
  'dome': 'mochi', 'tall': 'marsh', 'wide': 'squish', 'round': 'bun',
  'droopy': 'gumdrop', 'spire': 'acorn', 'comet': 'pebble', 'cape': 'helmet',
  'puff': 'cub', 'hooded': 'bell', 'classic': 'mochi', 'soft': 'bun',
  'cube': 'helmet', 'monitor': 'bell', 'egg': 'cub', 'pear': 'gumdrop',
  'plump': 'pebble', 'crest': 'acorn',
};

String lensbotShape(String shape) {
  if (lensbotShapes.contains(shape)) return shape;
  return legacyShapeToLensbot[shape] ?? 'mochi';
}

LensSpec lensSpec(String shape) {
  final id = lensbotShape(shape);
  return lensSpecs.firstWhere((s) => s.id == id);
}

const botRoles = [
  'general', 'tasks', 'code', 'seo', 'money', 'social', 'research', 'writer', //
];
const roleLabels = <String, String>{
  'general': 'General', 'tasks': 'Tasks', 'code': 'Code', 'seo': 'SEO',
  'money': 'Money', 'social': 'Social', 'research': 'Research', 'writer': 'Writer',
};

/// The editor's twelve swatches (palette.ts ROBOT_COLORS).
const robotColours = <(String, String)>[
  ('#8b5cf6', 'Violet'), ('#3b82f6', 'Blue'), ('#14b8a6', 'Teal'),
  ('#22c55e', 'Green'), ('#f97316', 'Orange'), ('#ec4899', 'Pink'),
  ('#ef4444', 'Red'), ('#eab308', 'Yellow'), ('#6366f1', 'Indigo'),
  ('#84cc16', 'Lime'), ('#ffffff', 'White'), ('#9ca3af', 'Grey'),
];
