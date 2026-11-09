import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/reachability.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/offline/offline_tasks_screen.dart';
import 'package:roost_mobile/features/offline/offline_screen.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../../fake_adapter.dart';
import '../../offline_test.dart' show homeAnswer, pumpApp;
import '../../workspace/workspace_fakes.dart';

Map<String, Object?> _task(String id, String title,
        {String bucket = 'today'}) =>
    {
      'id': id,
      'title': title,
      'status': 'todo',
      'priority': 'medium',
      'due_bucket': bucket,
    };

MemorySessionStore _store({List<String> notes = const []}) =>
    MemorySessionStore()
      ..url = 'http://127.0.0.1:18800'
      ..token = 'tok'
      ..offlineTasks = jsonEncode({
        'kept': [
          _task('t1', 'Pay rent'),
          _task('t2', 'File taxes', bucket: 'overdue'),
        ],
        'queue': <Object>[],
        'notes': notes,
      });

/// Home's answers, plus the sync's routes once Roost is back.
FakeReply _answer(RequestOptions o) {
  if (o.method == 'POST' && o.uri.path == '/api/tasks/offline') {
    final text = (o.data as Map)['text'];
    return FakeAdapter.json(
        {..._task('real1', '$text'), 'created': true}, status: 201);
  }
  if (o.method == 'POST' && o.uri.path.endsWith('/complete')) {
    return FakeAdapter.json({});
  }
  if (o.method == 'GET' && o.uri.path == '/api/tasks') {
    return FakeAdapter.json([_task('real1', 'buy milk')]);
  }
  return homeAnswer(o);
}

Future<void> _openTasks(WidgetTester tester) async {
  expect(find.byType(OfflineScreen), findsOneWidget);
  await tester.tap(find.byKey(const Key('offline-open-tasks')));
  await tester.pumpAndSettle();
  expect(find.byType(OfflineTasksScreen), findsOneWidget);
}

List<String> _posts(FakeAdapter a) => [
      for (final r in a.requests)
        if (r.method == 'POST') r.uri.path,
    ];

void main() {
  testWidgets('Open my tasks shows the kept list with no connection',
      (tester) async {
    await pumpApp(tester, SwitchAdapter(_answer, down: true), store: _store());
    await _openTasks(tester);
    expect(find.text('Pay rent'), findsOneWidget);
    expect(find.text('File taxes'), findsOneWidget);
    expect(find.text('Overdue'), findsOneWidget);
  });

  testWidgets('an add and a tick wait offline, then sync when Roost answers',
      (tester) async {
    final store = _store();
    final adapter = SwitchAdapter(_answer, down: true);
    await pumpApp(tester, adapter, store: store);
    await _openTasks(tester);

    await tester.enterText(
        find.byKey(const Key('offline-add-field')), 'buy milk tomorrow');
    await tester.tap(find.byKey(const Key('offline-add')));
    await tester.pumpAndSettle();
    expect(find.text('Waiting to sync'), findsOneWidget);
    expect(find.text('buy milk tomorrow'), findsOneWidget);

    await tester.tap(find.byKey(const Key('offline-check-t1')));
    await tester.pumpAndSettle();
    final kept = jsonDecode(store.offlineTasks!) as Map;
    expect([for (final q in kept['queue'] as List) q['kind']], ['add', 'done']);
    expect(_posts(adapter), isNot(contains('/api/tasks/offline')));

    // The offline screen beneath asks again; Roost answers and it syncs.
    adapter.down = false;
    await tester.pump(offlineRetryInterval);
    await tester.pumpAndSettle();
    expect(_posts(adapter),
        containsAllInOrder(['/api/tasks/offline', '/api/tasks/t1/complete']));
    expect((jsonDecode(store.offlineTasks!) as Map)['queue'], isEmpty);
    expect(find.text('Waiting to sync'), findsNothing);
    expect(find.text('buy milk'), findsOneWidget);
  });

  testWidgets('Couldn\'t sync lines show until dismissed', (tester) async {
    await pumpApp(tester, SwitchAdapter(_answer, down: true),
        store: _store(notes: ["Couldn't sync: bad line"]));
    await _openTasks(tester);
    expect(find.text("Couldn't sync: bad line"), findsOneWidget);
    await tester.tap(find.byKey(const Key('offline-notes-dismiss')));
    await tester.pumpAndSettle();
    expect(find.text("Couldn't sync: bad line"), findsNothing);
  });

  testWidgets('with nothing kept it says how to fill it', (tester) async {
    await pumpApp(tester, SwitchAdapter(_answer, down: true),
        store: MemorySessionStore()
          ..url = 'http://127.0.0.1:18800'
          ..token = 'tok');
    await _openTasks(tester);
    expect(find.byKey(const Key('offline-empty')), findsOneWidget);
  });

  testWidgets('the Tasks tab keeps each open list it loads (O2)',
      (tester) async {
    final store = MemorySessionStore();
    await pumpWorkspace(tester, const WorkspaceScreen(), [], session: store);
    final kept = jsonDecode(store.offlineTasks!) as Map;
    expect([for (final t in kept['kept'] as List) t['title']],
        ['Pay rent', 'Buy milk']);
  });
}
