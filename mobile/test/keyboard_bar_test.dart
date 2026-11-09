import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/computer/keyboard_bar.dart';
import 'package:roost_mobile/computer/keysyms.dart';
import 'package:roost_mobile/theme/app_theme.dart';

Widget _host(Widget child) => MaterialApp(
      theme: buildTheme(),
      home: Scaffold(body: Align(alignment: Alignment.bottomCenter, child: child)),
    );

void main() {
  testWidgets('a slim strip: extra keys, a hidden field, and Hide', (tester) async {
    final keys = <int>[];
    var hidden = false;
    await tester.binding.setSurfaceSize(const Size(390, 800));
    await tester.pumpWidget(_host(KeyboardBar(onKey: keys.add, onHide: () => hidden = true)));
    expect(tester.getSize(find.byType(KeyboardBar)).height, 44);
    await tester.tap(find.text('Esc'));
    await tester.enterText(find.byType(TextField), '​a');
    await tester.tap(find.byKey(const Key('keyboard-hide')));
    expect(keys.first, keyEscape);
    expect(keys.length, 2);
    expect(hidden, isTrue);
    expect(tester.takeException(), isNull);
  });
}
