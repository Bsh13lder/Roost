import 'package:flutter/material.dart';

/// Colours and sizes copied from web/src/styles/tokens.css. Dark only.
/// This is the one place for colours in the mobile app.
class Tokens {
  const Tokens._();

  // Surfaces, darkest first
  static const bg = Color(0xFF0E0E12);
  static const panel = Color(0xFF16161B);
  static const raised = Color(0xFF1F1F26);
  static const overlay = Color(0xFF1D1D24);
  static const scrim = Color(0x8C000000);

  // Text
  static const text = Color(0xFFEDEDF2);
  static const textSecondary = Color(0xFFA9A9B6);
  static const textFaint = Color(0xFF9292A0);

  // Lines
  static const border = Color(0xFF2A2A33);
  static const borderStrong = Color(0xFF3A3A45);

  // Accent
  static const accent = Color(0xFF6C5CE0);
  static const accentStrong = Color(0xFFB2A6F6);
  static const accentSoft = Color(0xFFC4B5FD);
  static const accentTint = Color(0x296C5CE0);
  static const onAccent = Color(0xFFFFFFFF);

  /// The accent choices in Settings. The first is the default; each fill
  /// keeps white text at 4.5:1, and its strong and soft shades read on the
  /// dark surfaces.
  static const accents = <AccentChoice>[
    AccentChoice('violet', 'Violet', accent, accentStrong, accentSoft),
    AccentChoice('blue', 'Blue', Color(0xFF2563EB), Color(0xFF93C5FD),
        Color(0xFFBFDBFE)),
    AccentChoice('teal', 'Teal', Color(0xFF0F766E), Color(0xFF5EEAD4),
        Color(0xFF99F6E4)),
    AccentChoice('green', 'Green', Color(0xFF15803D), Color(0xFF86EFAC),
        Color(0xFFBBF7D0)),
    AccentChoice('orange', 'Orange', Color(0xFFC2410C), Color(0xFFFDBA74),
        Color(0xFFFED7AA)),
    AccentChoice('pink', 'Pink', Color(0xFFDB2777), Color(0xFFF9A8D4),
        Color(0xFFFBCFE8)),
  ];
  static const accentTintAlpha = 0x29;

  // Meaning
  static const ok = Color(0xFF34D399);
  static const warn = Color(0xFFF5A524);
  static const danger = Color(0xFFF87171);
  static const dangerText = Color(0xFFFECACA);
  static const info = Color(0xFF60A5FA);
  static const off = Color(0xFF9CA3AF);
  static const dangerTint = Color(0x29F87171);
  static const warnTint = Color(0x29F5A524);
  static const warnText = Color(0xFFFDE68A);

  // Tasks: a check's ring is its priority, a due date's colour its day,
  // and a swipe shows green to finish or violet to move.
  static const prioUrgent = Color(0xFFF87171);
  static const prioHigh = Color(0xFFFB923C);
  static const prioMedium = Color(0xFF60A5FA);
  static const prioLow = Color(0xFF9292A0);
  static const ringFillAlpha = 0x1F;
  static const dueLate = Color(0xFFF87171);
  static const dueToday = Color(0xFF34D399);
  static const dueTomorrow = Color(0xFFC4B5FD);
  static const dueLater = Color(0xFFA9A9B6);
  static const swipeDone = Color(0xFF15803D);
  static const swipeLater = Color(0xFF6D28D9);

  // A call's End button (white icon on it at 4.5:1).
  static const callEnd = Color(0xFFDC2626);

  // Lensbots
  static const lensVisor = Color(0xFF161823);
  static const lensPupil = Color(0xFF14151D);
  static const lensSclera = Color(0xFFFFFFFF);
  static const lensHighlight = Color(0xFFFFFFFF);
  static const robotStar = Color(0xFFF6C453);

  // The light a shimmer sweeps with (the activity pill, the computer line).
  static const shimmerClear = Color(0x00FFFFFF);
  static const shimmerLight = Color(0x59FFFFFF);

  // Spacing (n x 4)
  static const space1 = 4.0;
  static const space2 = 8.0;
  static const space3 = 12.0;
  static const space4 = 16.0;
  static const space5 = 20.0;
  static const space6 = 24.0;
  static const space8 = 32.0;

  // Corners
  static const radiusSm = 8.0;
  static const radiusMd = 12.0;
  static const radiusLg = 20.0;

  // Tasks list sizes
  static const chipHeight = 32.0;
  static const chipBarHeight = 48.0;
  static const rowMinHeight = 56.0;
  static const checkSize = 22.0;
  static const rowIndent = 52.0;
  static const dotSize = 8.0;
  static const metaIcon = 13.0;

  // Type (rem * 16)
  static const fsCaption = 12.0;
  static const fsLabel = 13.0;
  static const fsRow = 15.0;
  static const fsBody = 14.0;
  static const fsLead = 16.0;
  static const fsHeading = 18.0;
  static const fsTitle = 22.0;
  static const fsDisplay = 28.0;
}

/// One accent colour the user may pick: the fill, the strong shade (accent
/// text, links, selection marks) and the soft shade (text on a tint).
class AccentChoice {
  const AccentChoice(this.id, this.label, this.accent, this.strong, this.soft);

  final String id;
  final String label;
  final Color accent;
  final Color strong;
  final Color soft;

  Color get tint => accent.withAlpha(Tokens.accentTintAlpha);
}
