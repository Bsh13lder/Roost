import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/theme/accent.dart';
import 'package:roost_mobile/theme/app_theme.dart';
import 'package:roost_mobile/theme/tokens.dart';
import 'package:roost_mobile/workspace/tasks/filter_pill.dart';

/// WCAG contrast of [fg] on [bg]; a see-through [bg] is laid on the page.
double contrast(Color fg, Color bg) {
  final solid = Color.alphaBlend(bg, Tokens.bg);
  final a = fg.computeLuminance(), b = solid.computeLuminance();
  final hi = a > b ? a : b, lo = a > b ? b : a;
  return (hi + 0.05) / (lo + 0.05);
}

void main() {
  test('every filter chip reads at 4.5:1, on and off, in every accent', () {
    for (final choice in Tokens.accents) {
      final accent = AccentColors.from(choice);
      for (final kind in PillKind.values) {
        for (final on in [true, false]) {
          final c = pillColors(kind, accent, on: on);
          expect(contrast(c.fg, c.bg), greaterThanOrEqualTo(4.5),
              reason: '${choice.id} ${kind.name} on=$on');
        }
      }
    }
  });

  test("the theme's selected-chip colours read at 4.5:1 in every accent", () {
    for (final choice in Tokens.accents) {
      final s = buildTheme(choice).colorScheme;
      expect(contrast(s.onSecondaryContainer, s.secondaryContainer),
          greaterThanOrEqualTo(4.5),
          reason: choice.id);
    }
  });

  testWidgets('a selected ChoiceChip on the accent tint is readable',
      (tester) async {
    final tint = AccentColors.from(Tokens.accents.first).tint;
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: ChoiceChip(
          label: const Text('Debt'),
          selected: true,
          selectedColor: tint,
          onSelected: (_) {},
        ),
      ),
    ));
    final p = tester.renderObject<RenderParagraph>(find.text('Debt'));
    expect(contrast(p.text.style!.color!, tint), greaterThanOrEqualTo(4.5));
  });
}
