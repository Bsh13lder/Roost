import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/task_drawer.dart';

import '../fake_adapter.dart';

Map<String, Object?> task({String? reminder}) => {
      'id': 't1',
      'title': 'Call Iurie',
      'status': 'todo',
      'priority': 'medium',
      'due_date': '2026-12-01T09:00:00+01:00',
      'reminder_at': reminder,
      'pre_reminders': <String>[],
      'steps': <Object>[],
      'tags': <String>[],
      'tainted': false,
      'created_at': '2026-10-23T10:00:00+00:00',
      'updated_at': '2026-10-23T10:00:00+00:00',
    };

void main() {
  late List<Map<String, dynamic>> patches;

  Future<void> pumpDrawer(WidgetTester tester, {String? reminder}) async {
    await tester.binding.setSurfaceSize(const Size(390, 1600));
    patches = [];
    final adapter = FakeAdapter((o) {
      if (o.path == '/api/tasks/t1' && o.method == 'PATCH') {
        patches.add((o.data as Map).cast<String, dynamic>());
        return FakeAdapter.json(task(reminder: '2026-12-01T07:50:00+00:00'));
      }
      if (o.path == '/api/tasks/t1') return FakeAdapter.json(task(reminder: reminder));
      return FakeAdapter.json([]);
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: TaskDrawer(taskId: 't1')),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('Remind me: 10 min before sends that time alone', (tester) async {
    await pumpDrawer(tester);
    expect(find.text('Off'), findsOneWidget);
    await tester.tap(find.byKey(const Key('drawer-remind')));
    await tester.pumpAndSettle();
    expect(find.text('At the due time'), findsOneWidget);
    expect(find.byKey(const Key('remind-off')), findsNothing);
    await tester.tap(find.byKey(const Key('remind-10 min before')));
    await tester.pumpAndSettle();
    expect(patches.single, {'reminder_at': '2026-12-01T08:50', 'pre_reminders': <String>[]});
  });

  testWidgets('Remind me shows when, and No reminder clears it', (tester) async {
    await pumpDrawer(tester, reminder: '2026-12-01T07:50:00+00:00');
    expect(find.text('Tue 1 Dec, 08:50'), findsOneWidget);
    await tester.tap(find.byKey(const Key('drawer-remind')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('remind-off')));
    await tester.pumpAndSettle();
    expect(patches.single, {'reminder_at': null});
  });
}
