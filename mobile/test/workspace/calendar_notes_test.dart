import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import 'workspace_fakes.dart';

void main() {
  testWidgets('notes: folders with counts open in place; typing filters',
      (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), <String>[]);
    await tester.tap(find.byKey(const Key('section-notes')));
    await tester.pumpAndSettle();
    expect(find.text('2 files'), findsOneWidget);
    expect(find.text('Upgrades'), findsNothing);
    await tester.tap(find.byKey(const Key('folder-p1')));
    await tester.pumpAndSettle();
    expect(find.text('Upgrades'), findsOneWidget);
    expect(find.text('Numbers'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('work-bar')), 'shop');
    await tester.pump();
    expect(find.text('Shopping list'), findsOneWidget);
    expect(find.text('Upgrades'), findsNothing);
    expect(find.byKey(const Key('new-note')), findsOneWidget);
  });
}
