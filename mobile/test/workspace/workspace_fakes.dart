import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/workspace/show_toggles.dart';
import 'package:roost_mobile/workspace/tasks/filter_store.dart';

import '../fake_adapter.dart';

/// The routine run's day: the 15th of this month, so the calendar (which
/// opens on this month) always shows it, in any time zone.
String get fakeRunDay {
  final now = DateTime.now();
  final month = now.month.toString().padLeft(2, '0');
  return '${now.year}-$month-15';
}

Map<String, Object?> wtask(String id, String title,
        {String? project, String? due = '2026-10-22', String bucket = 'today',
        String priority = 'medium'}) =>
    {
      'id': id,
      'title': title,
      'status': 'todo',
      'priority': priority,
      'due_date': due,
      'due_bucket': bucket,
      'project_id': project,
      'pre_reminders': <String>[],
      'tags': <String>[],
      'steps': <Object>[],
    };

Map<String, Object?> wproject(String id, String name,
        {bool pinned = false, String? color}) =>
    {
      'id': id,
      'name': name,
      'color': color,
      'currency': 'EUR',
      'status': 'active',
      'pinned': pinned,
      'total': {'budget': '100.00', 'spent': '40.00', 'remaining': '60.00', 'used_percent': 40, 'tone': 'ok'},
      'month': {'budget': null, 'spent': '10.00', 'remaining': null, 'used_percent': null, 'tone': 'ok'},
      'progress': {
        'total': 2, 'done': 1, 'overdue': 0, 'open': 1,
        'steps_total': 0, 'steps_done': 0, 'planned_total': '0',
      },
    };

/// Answers the Workspace's routes from fixed data; records every call.
FakeReply workspaceAnswer(RequestOptions o, List<String> calls) {
  final q = o.uri.query;
  calls.add('${o.method} ${o.uri.path}${q.isEmpty ? '' : '?$q'}');
  final key = '${o.method} ${o.uri.path}';
  switch (key) {
    case 'GET /api/tasks':
      if (q.contains('project_id=none')) {
        return FakeAdapter.json([wtask('t3', 'Loose end', due: null, bucket: 'none')]);
      }
      if (q.contains('project_id=p1')) {
        return FakeAdapter.json([wtask('t1', 'Pay rent', project: 'p1')]);
      }
      return FakeAdapter.json([
        wtask('t1', 'Pay rent', project: 'p1', priority: 'high'),
        wtask('t2', 'Buy milk', bucket: 'overdue', due: '2026-10-20'),
      ]);
    case 'GET /api/tasks/counts':
      return FakeAdapter.json({
        'overdue': 1, 'today': 1, 'upcoming_14': 0, 'someday': 0,
        'done_week': 0, 'open': 3,
      });
    case 'GET /api/projects':
      return FakeAdapter.json([wproject('p1', 'Club', color: '#34d399')]);
    case 'GET /api/projects/p1':
      return FakeAdapter.json({
        ...wproject('p1', 'Club'),
        'tasks': <Object>[],
        'expenses': [
          {
            'id': 'e1', 'amount': '12.50', 'currency': 'EUR', 'kind': 'expense',
            'description': 'Paint', 'project': 'Club', 'status': 'active',
          },
          {
            'id': 'e2', 'amount': '30.00', 'currency': 'EUR', 'kind': 'income',
            'description': 'Ticket sales', 'project': 'Club', 'status': 'active',
          },
        ],
        'notes': <Object>[],
        'documents': <Object>[],
      });
    case 'GET /api/notes':
      return FakeAdapter.json([
        {'id': 'n1', 'title': 'Upgrades', 'project_id': 'p1'},
        {'id': 'n2', 'title': 'Shopping list', 'project_id': null},
      ]);
    case 'GET /api/documents':
      return FakeAdapter.json([
        {'id': 'd1', 'title': 'Numbers', 'kind': 'sheet', 'project_id': 'p1'},
      ]);
    case 'GET /api/routines/occurrences':
      return FakeAdapter.json({
        'occurrences': [
          {
            'routine_id': 'r1', 'routine_name': 'Morning news', 'bot_id': 'b1', 'bot_name': 'Gela',
            'at': '${fakeRunDay}T07:00:00Z', 'day': fakeRunDay, 'time': '09:00', 'log_thread_id': 't-log',
          },
        ],
        'truncated': false,
      });
    case 'GET /api/day-notes':
      return FakeAdapter.json([
        {'id': 'dn1', 'day': '2026-10-22', 'author_kind': 'user', 'text': 'Market day'},
      ]);
    case 'POST /api/tasks/parse':
      return FakeAdapter.json({
        'title': 'Call Ana',
        'ready': true,
        'due_date': '2026-10-23',
        'due_text': 'Fri 23 Oct',
        'tags': <String>[],
      });
    case 'POST /api/tasks':
      return FakeAdapter.json(wtask('t9', 'Call Ana'), status: 201);
    case 'POST /api/tasks/t1/complete':
    case 'POST /api/tasks/t1/reopen':
      return FakeAdapter.json(wtask('t1', 'Pay rent'));
  }
  fail('unexpected ${o.method} ${o.uri}');
}

/// One test's own answers; null falls back to [workspaceAnswer].
typedef ExtraAnswer = FakeReply? Function(RequestOptions o);

Future<FakeAdapter> pumpWorkspace(
    WidgetTester tester, Widget home, List<String> calls,
    {ExtraAnswer? extra,
    TaskFilterStore? filterStore,
    ScreenToggleStore? toggleStore,
    SessionStore? session,
    List<Override> overrides = const [],
    Size size = const Size(1080, 2340)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final adapter =
      FakeAdapter((o) => extra?.call(o) ?? workspaceAnswer(o, calls));
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(session ?? MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    taskFilterStoreProvider.overrideWithValue(filterStore ?? MemoryTaskFilterStore()),
    screenToggleStoreProvider.overrideWithValue(toggleStore ?? MemoryScreenToggleStore()),
    ...overrides,
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(home: home),
  ));
  await tester.pumpAndSettle();
  return adapter;
}
