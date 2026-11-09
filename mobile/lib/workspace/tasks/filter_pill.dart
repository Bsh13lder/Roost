import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';

/// What a chip means, which picks its colour when on: Overdue is red, High
/// priority amber, the rest the accent.
enum PillKind { plain, late, high }

/// A chip's three colours. [bg] may be see-through; it lies on the page.
typedef PillColors = ({Color bg, Color fg, Color border});

/// Off: quiet panel and grey text. On: a tint with a light text of the same
/// hue, so the label always reads (tested at 4.5:1 in every accent).
PillColors pillColors(PillKind kind, AccentColors accent, {required bool on}) {
  if (!on) {
    return (bg: Tokens.panel, fg: Tokens.textSecondary, border: Tokens.border);
  }
  return switch (kind) {
    PillKind.late => (bg: Tokens.dangerTint, fg: Tokens.dangerText, border: Tokens.danger),
    PillKind.high => (bg: Tokens.warnTint, fg: Tokens.warnText, border: Tokens.warn),
    PillKind.plain => (bg: accent.tint, fg: accent.soft, border: accent.strong),
  };
}

/// One 32px filter chip: a ✓ when on (or the project's dot), its label and
/// an optional count.
class FilterPill extends StatelessWidget {
  const FilterPill({
    super.key,
    required this.label,
    required this.on,
    required this.onTap,
    this.kind = PillKind.plain,
    this.dot,
    this.count,
  });

  final String label;
  final bool on;
  final VoidCallback onTap;
  final PillKind kind;

  /// A project's colour, drawn as a dot before the label.
  final Color? dot;
  final int? count;

  @override
  Widget build(BuildContext context) {
    final c = pillColors(kind, AccentColors.of(context), on: on);
    return Semantics(
      selected: on,
      button: true,
      child: Material(
        color: c.bg,
        shape: StadiumBorder(side: BorderSide(color: c.border)),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            height: Tokens.chipHeight,
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              ..._lead(c.fg),
              Text(label,
                  style: TextStyle(
                      color: c.fg,
                      fontSize: Tokens.fsLabel,
                      fontWeight: on ? FontWeight.w600 : FontWeight.w500)),
              if (count != null && count! > 0) ...[
                const SizedBox(width: Tokens.space1),
                Text('$count',
                    style: TextStyle(
                        color: on ? c.fg : Tokens.textFaint,
                        fontSize: Tokens.fsCaption)),
              ],
            ]),
          ),
        ),
      ),
    );
  }

  List<Widget> _lead(Color fg) {
    if (on) {
      return [Icon(Icons.check, size: 14, color: fg), const SizedBox(width: Tokens.space1)];
    }
    if (dot == null) return const [];
    return [
      Container(
        width: Tokens.dotSize,
        height: Tokens.dotSize,
        decoration: BoxDecoration(color: dot, shape: BoxShape.circle),
      ),
      const SizedBox(width: Tokens.space2),
    ];
  }
}
