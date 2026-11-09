import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Screens read the accent from the theme (AccentColors.of / colorScheme),
/// so the colour picked in Settings reaches every one of them at once.
/// Only lib/theme/ names the fixed default accent, plus a server colour's
/// fallback that has no BuildContext.
const allowed = {'lib/board/common/widgets.dart:hexColor'};

void main() {
  test('no screen hard-codes the default accent', () {
    final offenders = <String>[];
    final files = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))
        .where((f) => !f.path.startsWith('lib/theme/'));
    for (final file in files) {
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (!RegExp(r'Tokens\.accent(Strong|Soft|Tint)?\b').hasMatch(lines[i])) continue;
        final inHex = file.path == 'lib/board/common/widgets.dart' &&
            lines[i].contains('Tokens.accent : Color(v)');
        if (inHex && allowed.contains('${file.path}:hexColor')) continue;
        offenders.add('${file.path}:${i + 1}');
      }
    }
    expect(offenders, isEmpty, reason: 'Read AccentColors.of(context) instead');
  });
}
