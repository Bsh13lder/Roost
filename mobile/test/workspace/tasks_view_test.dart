import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/workspace/tasks/filter_store.dart';
import 'package:roost_mobile/workspace/tasks/task_filter.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../fake_adapter.dart';
import 'workspace_fakes.dart';

const tall = Size(1080, 3600);

/// One task in each section, two projects, and one done task.
FakeReply? richAnswer(RequestOptions o, {bool empty = false}) {
  final key = '${o.method} ${o.uri.path}';
  if (key == 'GET /api/tasks' && o.uri.query == 'sort=due') {
    if (empty) return FakeAdapter.json(<Object>[]);
    return FakeAdapter.json([
      wtask('o1', 'File taxes', bucket: 'overdue', due: '2026-10-20',
          priority: 'urgent', project: 'p1'),
      {
        ...wtask('d1', 'Pay rent', project: 'p1', priority: 'high'),
        'repeat_text': 'Every month',
        'comment_count': 3,
        'steps': [
          {'id': 's1', 'title': 'a', 'done': true},
          for (final i in [2, 3, 4]) {'id': 's$i', 'title': 'b', 'done': false},
        ],
      },
      wtask('m1', 'Call Ana', bucket: 'tomorrow', due: '2026-10-23T09:00:00+02:00'),
      wtask('l1', 'Book flights', bucket: 'week', due: '2026-10-27',
          priority: 'low', project: 'p2'),
      wtask('n1', 'Read book', bucket: 'none', due: null),
    ]);
  }
  if (key == 'GET /api/tasks' && o.uri.query == 'view=done') {
    return FakeAdapter.json([
      {...wtask('x1', 'Old thing'), 'status': 'done'},
    ]);
  }
  if (key == 'GET /api/projects') {
    return FakeAdapter.json([
      wproject('p1', 'Club', color: '#34d399'),
      wproject('p2', 'Home', color: '#60a5fa'),
    ]);
  }
  final done = RegExp(r'^POST /api/tasks/(\w+)/(complete|reopen)$').firstMatch(key);
  if (done != null) return FakeAdapter.json(wtask(done.group(1)!, 'x'));
  if (o.method == 'PATCH' && o.uri.path == '/api/tasks/d1') {
    return FakeAdapter.json(wtask('d1', 'Pay rent'));
  }
  if (key == 'POST /api/tasks/move-overdue') {
    return FakeAdapter.json({'moved': <Object>[]});
  }
  return null;
}

Future<FakeAdapter> pumpRich(WidgetTester tester, List<String> calls,
    {TaskFilterStore? store, bool empty = false}) {
  return pumpWorkspace(tester, const WorkspaceScreen(), calls,
      size: tall,
      filterStore: store,
      extra: (o) {
        final r = richAnswer(o, empty: empty);
        if (r != null) calls.add('${o.method} ${o.uri.path}${o.uri.query.isEmpty ? '' : '?${o.uri.query}'}');
        return r;
      });
}

Future<void> tapKey(WidgetTester tester, String key) async {
  final f = find.byKey(Key(key));
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

bool shows(String title) => find.text(title).evaluate().isNotEmpty;

List<String> shown() => [
      for (final title in const [
        'File taxes', 'Pay rent', 'Call Ana', 'Book flights', 'Read book', 'Old thing',
      ])
        if (shows(title)) title,
    ];

void main() {
  testWidgets('opens on every open task, in Todoist-style day sections',
      (tester) async {
    final calls = <String>[];
    await pumpRich(tester, calls);
    expect(calls, contains('GET /api/tasks?sort=due'));
    expect(calls.where((c) => c.contains('view=today')), isEmpty);
    final keys = ['overdue', 'today', 'tomorrow', '2026-10-27', 'none'];
    final ys = [
      for (final k in keys) tester.getTopLeft(find.byKey(Key('section-$k'))).dy,
    ];
    expect([...ys]..sort(), ys);
    for (final title in ['Overdue', 'Today', 'Tomorrow', 'Tue 27 Oct', 'No date']) {
      expect(find.text(title), findsWidgets);
    }
    expect(shown(), ['File taxes', 'Pay rent', 'Call Ana', 'Book flights', 'Read book']);
    expect(tester.widget<Text>(find.byKey(const Key('tasks-count'))).data, '5');
    // The old tab line is gone.
    expect(find.byKey(const Key('wtab-today')), findsNothing);
  });

  testWidgets('a row: steps, repeat, due in words, the project on the right',
      (tester) async {
    await pumpRich(tester, <String>[]);
    expect(find.descendant(
        of: find.byKey(const Key('steps-d1')), matching: find.text('1/4')),
        findsOneWidget);
    expect(find.byKey(const Key('repeat-d1')), findsOneWidget);
    expect(find.descendant(
        of: find.byKey(const Key('due-m1')), matching: find.text('Tomorrow 09:00')),
        findsOneWidget);
    expect(find.descendant(
        of: find.byKey(const Key('pill-d1')), matching: find.text('Club')),
        findsOneWidget);
    expect(find.byKey(const Key('pill-n1')), findsNothing);
    expect(find.descendant(
        of: find.byKey(const Key('comments-d1')), matching: find.text('3')),
        findsOneWidget);
    expect(find.byKey(const Key('comments-n1')), findsNothing);
  });

  testWidgets('date chips filter and combine as OR', (tester) async {
    await pumpRich(tester, <String>[]);
    await tapKey(tester, 'fchip-today');
    expect(shown(), ['Pay rent']);
    await tapKey(tester, 'fchip-overdue');
    expect(shown(), ['File taxes', 'Pay rent']);
    await tapKey(tester, 'fchip-today');
    await tapKey(tester, 'fchip-overdue');
    await tapKey(tester, 'fchip-upcoming');
    expect(shown(), ['Call Ana', 'Book flights']);
    await tapKey(tester, 'fchip-upcoming');
    await tapKey(tester, 'fchip-nodate');
    expect(shown(), ['Read book']);
  });

  testWidgets('High priority and a project narrow; No project is the Inbox',
      (tester) async {
    await pumpRich(tester, <String>[]);
    await tapKey(tester, 'fchip-high');
    expect(shown(), ['File taxes', 'Pay rent']);
    await tapKey(tester, 'fchip-high');
    await tapKey(tester, 'fchip-p-p2');
    expect(shown(), ['Book flights']);
    await tapKey(tester, 'fchip-p-p2');
    await tapKey(tester, 'fchip-p-none');
    expect(shown(), ['Call Ana', 'Read book']);
  });

  testWidgets('Done asks for the done list and shows it', (tester) async {
    final calls = <String>[];
    await pumpRich(tester, calls);
    await tapKey(tester, 'fchip-done');
    expect(calls, contains('GET /api/tasks?view=done'));
    expect(shown(), ['Old thing']);
  });

  testWidgets('no match: a friendly line and Clear filters brings all back',
      (tester) async {
    await pumpRich(tester, <String>[]);
    await tapKey(tester, 'fchip-nodate');
    await tapKey(tester, 'fchip-p-p1');
    expect(find.text('No tasks match these filters'), findsOneWidget);
    await tapKey(tester, 'filters-clear');
    expect(shown().length, 5);
  });

  testWidgets('while chips are on, a first chip shows how many and clears them',
      (tester) async {
    await pumpRich(tester, <String>[]);
    expect(find.byKey(const Key('fchip-clear')), findsNothing);
    await tapKey(tester, 'fchip-today');
    await tapKey(tester, 'fchip-p-p2');
    expect(find.descendant(
        of: find.byKey(const Key('fchip-clear')), matching: find.text('2')),
        findsOneWidget);
    await tapKey(tester, 'fchip-clear');
    expect(shown().length, 5);
    expect(find.byKey(const Key('fchip-clear')), findsNothing);
  });

  testWidgets('an empty list says all clear', (tester) async {
    await pumpRich(tester, <String>[], empty: true);
    expect(find.text('All clear. Nothing on your list.'), findsOneWidget);
    await tapKey(tester, 'fchip-today');
    expect(find.text('All clear for today'), findsOneWidget);
  });

  testWidgets('a tapped chip is kept on the phone', (tester) async {
    final store = MemoryTaskFilterStore();
    await pumpRich(tester, <String>[], store: store);
    await tapKey(tester, 'fchip-today');
    expect(store.saved, const TaskFilter().toggleDate(DateFilter.today));
  });

  testWidgets('the kept chips are on when Tasks opens again', (tester) async {
    final store = MemoryTaskFilterStore(const TaskFilter().toggleDate(DateFilter.today));
    await pumpRich(tester, <String>[], store: store);
    expect(shown(), ['Pay rent']);
  });

  testWidgets('swipe right completes, with Undo', (tester) async {
    final calls = <String>[];
    await pumpRich(tester, calls);
    await tester.drag(find.byKey(const Key('row-d1')), const Offset(300, 0));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /api/tasks/d1/complete'));
    expect(find.text('Done: Pay rent'), findsOneWidget);
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /api/tasks/d1/reopen'));
  });

  testWidgets('swipe left opens the reschedule sheet', (tester) async {
    final calls = <String>[];
    final adapter = await pumpRich(tester, calls);
    await tester.drag(find.byKey(const Key('row-d1')), const Offset(-300, 0));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pick-Tomorrow')), findsOneWidget);
    await tester.tap(find.byKey(const Key('pick-No date')));
    await tester.pumpAndSettle();
    final patch = adapter.requests.lastWhere((r) => r.method == 'PATCH');
    expect(patch.data, {'due_date': null});
    expect(find.text('Pay rent'), findsOneWidget);
  });

  testWidgets('the checkbox completes with Undo', (tester) async {
    final calls = <String>[];
    await pumpRich(tester, calls);
    await tester.tap(find.byKey(const Key('check-o1')));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /api/tasks/o1/complete'));
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /api/tasks/o1/reopen'));
  });

  testWidgets('Overdue offers Reschedule; a header folds its section',
      (tester) async {
    await pumpRich(tester, <String>[]);
    await tapKey(tester, 'reschedule-all');
    expect(find.text('Reschedule all overdue'), findsOneWidget);
    await tester.tap(find.byKey(const Key('pick-Today')));
    await tester.pumpAndSettle();

    await tapKey(tester, 'section-today');
    expect(shows('Pay rent'), isFalse);
    await tapKey(tester, 'section-today');
    expect(shows('Pay rent'), isTrue);
  });

  testWidgets('long-press offers Move to project, Reschedule and Delete',
      (tester) async {
    await pumpRich(tester, <String>[]);
    await tester.longPress(find.text('Pay rent'));
    await tester.pumpAndSettle();
    for (final item in ['move', 'reschedule', 'delete']) {
      expect(find.byKey(Key('menu-$item')), findsOneWidget);
    }
  });

  testWidgets('the layout menu switches to Kanban and to the Calendar',
      (tester) async {
    await pumpRich(tester, <String>[]);
    await tapKey(tester, 'layout-menu');
    await tester.tap(find.text('Kanban'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('group-status')), findsOneWidget);
    expect(find.byKey(const Key('fchip-today')), findsNothing);

    await tapKey(tester, 'layout-menu');
    await tester.tap(find.text('Calendar'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('month-grid')), findsOneWidget);
  });

  testWidgets('the bar filters as you type and Enter adds the server reading',
      (tester) async {
    final calls = <String>[];
    final adapter = await pumpWorkspace(tester, const WorkspaceScreen(), calls);
    await tester.enterText(find.byKey(const Key('work-bar')), 'rent');
    await tester.pump();
    expect(find.text('Pay rent'), findsOneWidget);
    expect(find.text('Buy milk'), findsNothing);

    await tester.enterText(find.byKey(const Key('work-bar')), 'Call Ana friday');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.text('Due Fri 23 Oct'), findsOneWidget);
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    final create = adapter.requests
        .lastWhere((r) => r.method == 'POST' && r.uri.path == '/api/tasks');
    expect(create.data, {'title': 'Call Ana', 'due_date': '2026-10-23'});
  });

  testWidgets('the picker row shows on Tasks and Calendar, never on Notes',
      (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), <String>[]);
    await tester.tap(find.byKey(const Key('work-bar')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('qp-help')), findsOneWidget);

    await tester.tap(find.byKey(const Key('section-notes')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('work-bar')));
    await tester.enterText(find.byKey(const Key('work-bar')), 'Upg');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('qp-help')), findsNothing);

    await tester.tap(find.byKey(const Key('section-calendar')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('work-bar')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('qp-help')), findsOneWidget);
  });

  testWidgets('the bar switches between Tasks, Notes and Calendar',
      (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), <String>[]);
    await tester.tap(find.byKey(const Key('section-notes')));
    await tester.pumpAndSettle();
    expect(find.text('Club'), findsWidgets);
    expect(find.text('No project'), findsOneWidget);

    await tester.tap(find.byKey(const Key('section-calendar')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('month-grid')), findsOneWidget);
  });
}
