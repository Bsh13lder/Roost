// Board toggles (2026-10-26): routine runs on the calendars, Show per
// screen, and the bot's name on a task it made.
import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/kanban_groups.dart';
import 'package:roost_mobile/board/tasks/task_dates.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/plan/plan_calendar.dart';
import 'package:roost_mobile/plan/plan_models.dart';
import 'package:roost_mobile/routines/occurrences.dart';
import 'package:roost_mobile/workspace/calendar/calendar_view.dart';
import 'package:roost_mobile/workspace/calendar/day_cell.dart';
import 'package:roost_mobile/workspace/calendar/day_marks.dart';
import 'package:roost_mobile/workspace/calendar/day_panel.dart';
import 'package:roost_mobile/workspace/show_toggles.dart';
import 'package:roost_mobile/workspace/tasks/tasks_data.dart';
import 'package:roost_mobile/workspace/tasks/todo_meta.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../fake_adapter.dart';
import 'tasks_view_test.dart' show pumpRich, tall, tapKey;
import 'workspace_fakes.dart';

Map<String, dynamic> occ(String id, String day, String time, {String name = 'Morning news'}) => {
      'routine_id': id, 'routine_name': name, 'bot_id': 'b1', 'bot_name': 'Gela',
      'at': '${day}T$time:00Z', 'day': day, 'time': time, 'log_thread_id': 't-$id',
    };

TaskItem item(String id, {String status = 'todo', String? bot, String? due = '2026-10-23T17:00:00+02:00'}) =>
    TaskItem(id: id, title: id, status: status, priority: 'medium', dueDate: due, createdByBot: bot);

PlanItem pitem(String text, {required String status, String? date}) =>
    PlanItem(id: text, status: status, text: text, tags: const [], date: date, time: null, tainted: false);

class _SeededLive extends LiveController {
  @override
  LiveState build() => LiveState(bots: {
        'b1': Bot.fromJson({'id': 'b1', 'name': 'Gela', 'status': 'resting'}),
      });
}

void main() {
  test('routine rows group once a day per routine, times in order', () {
    final days = groupRoutineDays([
      occ('r1', '2026-10-23', '15:00'),
      occ('r1', '2026-10-23', '09:00'),
      occ('r2', '2026-10-23', '08:00', name: 'Gym'),
      {'routine_id': 'bad'},
    ]);
    final friday = days['2026-10-23']!;
    expect([for (final e in friday) e.routineName], ['Gym', 'Morning news']);
    expect(friday[1].times, ['09:00', '15:00']);
    expect(friday[1].timeWords, '09:00 +1');
    expect(friday[0].timeWords, '08:00');
    expect(days.length, 1);
  });

  test('ScreenToggles read leniently, flip immutably and round-trip', () {
    expect(ScreenToggles.fromJson('nonsense'), const ScreenToggles());
    final t = ScreenToggles.fromJson({'done': false});
    expect((t.routines, t.done, t.botMade), (true, false, true));
    final flipped = t.flip(ShowToggle.routines);
    expect(flipped.routines, isFalse);
    expect(t.routines, isTrue);
    expect(ScreenToggles.fromJson(flipped.toJson()), flipped);
    expect(flipped.hashCode, ScreenToggles.fromJson(flipped.toJson()).hashCode);
    expect(ShowToggle.values.map((v) => flipped.shows(v)), [false, false, true]);
  });

  test('the controller picks up what the phone kept and saves each flip per screen', () async {
    final store = MemoryScreenToggleStore({screenCalendar: const ScreenToggles(done: false)});
    final container = ProviderContainer(overrides: [screenToggleStoreProvider.overrideWithValue(store)]);
    addTearDown(container.dispose);
    container.read(screenTogglesProvider(screenCalendar));
    await Future<void>.delayed(Duration.zero);
    expect(container.read(screenTogglesProvider(screenCalendar)).done, isFalse);
    container.read(screenTogglesProvider(screenTasks).notifier).flip(ShowToggle.botMade);
    expect(store.saved[screenTasks]!.botMade, isFalse);
    expect(store.saved[screenCalendar]!.botMade, isTrue);
  });

  test('keepMade, calendarTasks, monthSpan, botTasks, planCounts and addPlanMarks', () {
    final rows = [item('mine'), item('bots', bot: 'b1'), item('old', status: 'done')];
    expect(keepMade(rows, show: true), same(rows));
    expect([for (final t in keepMade(rows, show: false)) t.id], ['mine', 'old']);
    expect([for (final t in calendarTasks(rows, const ScreenToggles(done: false, botMade: false), '')) t.id],
        ['mine']);
    expect([for (final t in calendarTasks(rows, const ScreenToggles(), 'bo')) t.id], ['bots']);
    expect(monthSpan('2026-02', botId: 'b1'), (from: '2026-02-01', to: '2026-02-28', botId: 'b1'));
    expect([for (final t in botTasks(rows, 'b1')) t.id], ['bots']);
    final plan = [
      pitem('a', status: 'planned', date: '2026-10-25'),
      pitem('b', status: 'done', date: '2026-10-25'),
      pitem('c', status: 'dropped', date: '2026-10-25'),
      pitem('d', status: 'planned'),
    ];
    expect(planCounts(plan, done: true), {'2026-10-25': 2});
    expect(planCounts(plan, done: false), {'2026-10-25': 1});
    final day = DateTime.utc(2026, 10, 25);
    final marks = addPlanMarks({day: const DayMarks(routines: 1)}, {'2026-10-25': 2, '2026-10-26': 1});
    expect((marks[day]!.routines, marks[day]!.plans), (1, 2));
    expect(marks[DateTime.utc(2026, 10, 26)]!.isEmpty, isFalse);
  });

  testWidgets("the day panel lists the day's routine runs and names a bot's task",
      (tester) async {
    final day = DateTime.utc(2026, 10, 23);
    final runs = groupRoutineDays([occ('r1', '2026-10-23', '15:00')]);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: DayPanel(
            day: day,
            today: day,
            onAddNote: () {},
            notes: const [],
            plan: dayPlan(day, [item('Lunch', due: '2026-10-23T13:30:00+02:00'), item('Draft', bot: 'b1')],
                runs, day),
            bots: const {'b1': BotTag(name: 'Gela', color: '#22c55e')},
          ),
        ),
      ),
    ));
    final routine = find.byKey(const Key('routine-r1'));
    expect(routine, findsOneWidget);
    expect(find.descendant(of: routine, matching: find.text('Gela')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('ptask-Draft')), matching: find.text('Gela')),
        findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('ptask-Lunch')), matching: find.text('Gela')),
        findsNothing);
  });

  testWidgets('a routine line opens the run log', (tester) async {
    final entry = groupRoutineDays([occ('r1', '2026-10-23', '09:00')])['2026-10-23']!.single;
    final router = GoRouter(routes: [
      GoRoute(path: '/', builder: (_, _) => Scaffold(body: RoutineLine(entry: entry, showBot: false))),
      GoRoute(
          path: '/bots/:botId/routines/:routineId/log',
          builder: (_, s) => Text('log ${s.pathParameters['botId']} ${s.pathParameters['routineId']}')),
    ]);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    expect(find.text('Gela'), findsNothing);
    await tester.tap(find.byKey(const Key('routine-r1')));
    await tester.pumpAndSettle();
    expect(find.text('log b1 r1'), findsOneWidget);
  });

  testWidgets("a row's meta names the bot that made it", (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: TodoMeta(task: item('t1', bot: 'b1'), maker: 'Gela')),
    ));
    expect(find.descendant(of: find.byKey(const Key('maker-t1')), matching: find.text('Gela')),
        findsOneWidget);
    expect(TodoMeta(task: item('t2', due: null)).isEmpty, isTrue);
    expect(TodoMeta(task: item('t2', due: null), maker: 'Gela').isEmpty, isFalse);
  });

  test('routine days ask with the bot, and a failure is no lines', () async {
    var down = false;
    final adapter = FakeAdapter((o) => down
        ? FakeAdapter.json({'detail': 'no'}, status: 500)
        : FakeAdapter.json({'occurrences': [occ('r1', '2026-10-23', '09:00')], 'truncated': false}));
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    const span = (from: '2026-10-01', to: '2026-10-31', botId: 'b1');
    final days = await container.read(routineDaysProvider(span).future);
    expect(days['2026-10-23']!.single.routineId, 'r1');
    expect(adapter.requests.last.uri.queryParameters,
        {'from': '2026-10-01', 'to': '2026-10-31', 'bot_id': 'b1'});
    down = true;
    const other = (from: '2026-11-01', to: '2026-11-30', botId: null);
    expect(await container.read(routineDaysProvider(other).future), isEmpty);
    expect(adapter.requests.last.uri.queryParameters.containsKey('bot_id'), isFalse);
  });

  testWidgets("the Plan calendar is a month grid; today's panel lists its Plan, tasks and routines",
      (tester) async {
    tester.view.physicalSize = tall;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final day = isoDay(appToday());
    final adapter = FakeAdapter((o) => o.uri.path == '/api/tasks'
        ? FakeAdapter.json([
            {...wtask('t1', 'Gela task'), 'due_date': '${day}T10:00:00Z', 'created_by_bot': 'b1'},
            {...wtask('t2', 'Someone else'), 'due_date': '${day}T10:00:00Z', 'created_by_bot': 'b2'},
          ])
        : FakeAdapter.json({'occurrences': [occ('r1', day, '23:59')], 'truncated': false}));
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
      screenToggleStoreProvider.overrideWithValue(MemoryScreenToggleStore()),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: Scaffold(
          body: PlanCalendarPane(botId: 'b1', items: [
            pitem('Filed taxes', status: 'done', date: day),
            pitem('Someday idea', status: 'planned'),
          ]),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    final occurrences = adapter.requests.where((r) => r.uri.path != '/api/tasks');
    expect(occurrences.single.uri.queryParameters['bot_id'], 'b1');
    expect(find.byKey(const Key('month-grid')), findsOneWidget);
    expect(find.byKey(const Key('calendar-legend')), findsOneWidget);
    expect(find.text('Morning news'), findsOneWidget);
    expect(find.text('Filed taxes'), findsOneWidget);
    expect(find.text('Gela task'), findsOneWidget);
    expect(find.text('Someone else'), findsNothing);
    expect(find.text('Someday idea'), findsOneWidget); // No date
    expect(find.byKey(Key('plan-$day-0')), findsOneWidget);
    await tester.tap(find.byKey(const Key('show-menu-plan')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('show-done')));
    await tester.pumpAndSettle();
    expect(find.text('Filed taxes'), findsNothing);
    await tester.tap(find.byKey(const Key('show-menu-plan')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('show-routines')));
    await tester.pumpAndSettle();
    expect(find.text('Morning news'), findsNothing);
    expect(find.text('Gela task'), findsOneWidget);
  });

  testWidgets('Tasks: Show › Made by bots hides a bot\'s task and names the bot otherwise',
      (tester) async {
    final calls = <String>[];
    final store = MemoryScreenToggleStore();
    await pumpWorkspace(tester, const WorkspaceScreen(), calls,
        size: tall,
        toggleStore: store,
        overrides: [liveProvider.overrideWith(_SeededLive.new)],
        extra: (RequestOptions o) => '${o.method} ${o.uri.path}' == 'GET /api/tasks' && o.uri.query == 'sort=due'
            ? FakeAdapter.json([
                wtask('t1', 'Pay rent'),
                {...wtask('t2', 'Draft the post'), 'created_by_bot': 'b1'},
              ])
            : null);
    expect(find.descendant(of: find.byKey(const Key('maker-t2')), matching: find.text('Gela')),
        findsOneWidget);
    await tapKey(tester, 'show-menu-tasks');
    await tester.tap(find.byKey(const Key('show-botMade')));
    await tester.pumpAndSettle();
    expect(find.text('Draft the post'), findsNothing);
    expect(find.text('Pay rent'), findsOneWidget);
    expect(store.saved[screenTasks]!.botMade, isFalse);
  });

  testWidgets('the Workspace calendar shows routine runs; Show › Routines hides them',
      (tester) async {
    final calls = <String>[];
    await pumpRich(tester, calls);
    await tapKey(tester, 'layout-menu');
    await tester.tap(find.text('Calendar'));
    await tester.pumpAndSettle();
    expect(calls.where((c) => c.startsWith('GET /api/routines/occurrences?from=')), isNotEmpty);
    await tester.tap(find.byKey(Key('day-$fakeRunDay')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('routine-r1')), findsOneWidget);
    await tapKey(tester, 'show-menu-calendar');
    await tester.tap(find.byKey(const Key('show-routines')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('routine-r1')), findsNothing);
  });

  test('kanbanShown leaves out done and bot-made cards only when hidden', () {
    final rows = [item('mine'), item('bots', bot: 'b1'), item('old', status: 'done'), item('failed', status: 'failed')];
    expect(kanbanShown(rows, done: true, botMade: true), same(rows));
    expect([for (final t in kanbanShown(rows, done: false, botMade: true)) t.id], ['mine', 'bots']);
    expect([for (final t in kanbanShown(rows, done: true, botMade: false)) t.id], ['mine', 'old', 'failed']);
    expect([for (final t in kanbanShown(rows, done: false, botMade: false)) t.id], ['mine']);
  });

  testWidgets('Kanban: Show › Done and Made by bots hide those cards, kept for the Kanban alone',
      (tester) async {
    final calls = <String>[];
    final store = MemoryScreenToggleStore();
    await pumpWorkspace(tester, const WorkspaceScreen(), calls,
        size: tall,
        toggleStore: store,
        extra: (RequestOptions o) => '${o.method} ${o.uri.path}' == 'GET /api/tasks' &&
                o.uri.queryParameters['view'] == 'board'
            ? FakeAdapter.json([
                wtask('t1', 'Pay rent'),
                {...wtask('t2', 'Draft the post'), 'created_by_bot': 'b1'},
                {...wtask('t3', 'Filed taxes'), 'status': 'done'},
              ])
            : null);
    await tapKey(tester, 'layout-menu');
    await tester.tap(find.text('Kanban'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('group-due'))); // every card in Today, on screen
    await tester.pumpAndSettle();
    expect(find.text('Draft the post'), findsOneWidget);
    expect(find.text('Filed taxes'), findsOneWidget);
    expect(find.byKey(const Key('show-menu-tasks')), findsNothing);

    await tapKey(tester, 'show-menu-kanban');
    expect(find.byKey(const Key('show-routines')), findsNothing);
    await tester.tap(find.byKey(const Key('show-botMade')));
    await tester.pumpAndSettle();
    expect(find.text('Draft the post'), findsNothing);
    expect(find.text('Pay rent'), findsOneWidget);

    await tapKey(tester, 'show-menu-kanban');
    await tester.tap(find.byKey(const Key('show-done')));
    await tester.pumpAndSettle();
    expect(find.text('Filed taxes'), findsNothing);
    expect(find.byKey(const Key('column-today')), findsOneWidget);
    expect(store.saved[screenKanban], const ScreenToggles(done: false, botMade: false));
    expect(store.saved.containsKey(screenTasks), isFalse);
  });
}
