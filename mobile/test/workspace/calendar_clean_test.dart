// The clean calendar (2026-10-26): day cells hold markers only, a tapped
// day opens Tasks · Reminders · Routines, and one line explains the marks.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_dates.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/routines/occurrences.dart';
import 'package:roost_mobile/workspace/calendar/calendar_legend.dart';
import 'package:roost_mobile/workspace/calendar/day_cell.dart';
import 'package:roost_mobile/workspace/calendar/day_marks.dart';
import 'package:roost_mobile/workspace/calendar/day_notes_api.dart';
import 'package:roost_mobile/workspace/calendar/day_panel.dart';
import 'package:roost_mobile/workspace/calendar/month_grid_view.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../fake_adapter.dart';
import 'tasks_view_test.dart' show richAnswer, tall, tapKey;
import 'workspace_fakes.dart';

TaskItem t(String id,
        {String? due = '2026-10-23',
        String status = 'todo',
        String priority = 'medium',
        String? project,
        String? remind,
        String? bot}) =>
    TaskItem(
        id: id,
        title: 'Title $id',
        status: status,
        priority: priority,
        dueDate: due,
        projectId: project,
        reminderAt: remind,
        createdByBot: bot);

Map<String, dynamic> occ(String id, String day, String time) => {
      'routine_id': id, 'routine_name': 'Morning news', 'bot_id': 'b1', 'bot_name': 'Gela',
      'at': '${day}T$time:00Z', 'day': day, 'time': time,
    };

const bots = {'b1': BotTag(name: 'Gela', color: '#22c55e')};
final today = DateTime.utc(2026, 10, 23);

Widget host(Widget child) => MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  testWidgets('a crowded day: three dots and +N, a bell, a repeat and the bot, no titles',
      (tester) async {
    final tasks = [
      t('a', priority: 'urgent'),
      t('b', bot: 'b1'),
      t('c', project: 'p1'),
      t('d'),
      t('e', status: 'done'),
      t('r', due: '2026-11-03', remind: '2026-10-23T07:00:00Z'),
    ];
    final marks = buildDayMarks(
        tasks: tasks, routines: groupRoutineDays([occ('r1', '2026-10-23', '09:00')]), today: today);
    DateTime? picked;
    await tester.pumpWidget(host(MonthGridView(
      month: '2026-10',
      today: today,
      selected: today,
      marks: marks,
      bots: bots,
      projectColors: const {'p1': '#60a5fa'},
      onPick: (d) => picked = d,
    )));
    expect(find.byKey(const Key('dot-a')), findsOneWidget);
    expect(find.byKey(const Key('dot-c')), findsOneWidget);
    expect(find.byKey(const Key('dot-d')), findsNothing);
    expect(tester.widget<Text>(find.byKey(const Key('more-2026-10-23'))).data, '+2');
    expect(find.byKey(const Key('bell-2026-10-23')), findsOneWidget);
    expect(find.byKey(const Key('repeat-2026-10-23')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('bot-2026-10-23')), matching: find.text('G')),
        findsOneWidget);
    expect(find.byKey(const Key('bell-2026-10-22')), findsNothing);
    expect(find.textContaining('Title'), findsNothing);
    expect(find.bySemanticsLabel('Fri 23 Oct: 5 tasks, 1 reminder, 1 routine'), findsOneWidget);
    await tester.tap(find.byKey(const Key('day-2026-10-19')));
    expect(picked, DateTime.utc(2026, 10, 19));
  });

  testWidgets('a done task is a ring, an open one a filled dot', (tester) async {
    final marks = buildDayMarks(tasks: [t('open'), t('shut', status: 'done')], routines: const {}, today: today);
    await tester.pumpWidget(host(MonthGridView(
        month: '2026-10', today: today, selected: today, marks: marks, onPick: (_) {})));
    BoxDecoration deco(String id) =>
        tester.widget<Container>(find.byKey(Key('dot-$id'))).decoration! as BoxDecoration;
    expect(deco('open').color, isNotNull);
    expect(deco('shut').color, isNull);
    expect(deco('shut').border, isNotNull);
  });

  testWidgets('a folded grid shows only the chosen week', (tester) async {
    await tester.pumpWidget(host(MonthGridView(
        month: '2026-10', today: today, selected: today, marks: const {}, collapsed: true, onPick: (_) {})));
    expect(find.byKey(const Key('day-2026-10-19')), findsOneWidget);
    expect(find.byKey(const Key('day-2026-10-5')), findsNothing);
  });

  testWidgets('the day panel: Tasks, Reminders, Routines with time, bot and project', (tester) async {
    String? opened;
    final tasks = [
      t('late', due: '2026-10-20', bot: 'b1', project: 'p1'),
      t('timed', due: '2026-10-23T18:30:00+02:00'),
      t('ping', due: '2026-10-30', remind: '2026-10-23T07:00:00Z', project: 'p1'),
    ];
    final plan = dayPlan(today, tasks, groupRoutineDays([occ('r1', '2026-10-23', '09:00')]), today);
    await tester.pumpWidget(host(DayPanel(
      day: today,
      today: today,
      plan: plan,
      notes: [DayNote(id: 'n1', day: today, text: 'Market day')],
      bots: bots,
      projectNames: const {'p1': 'Club'},
      onAddNote: () {},
      onOpenTask: (id) => opened = id,
    )));
    expect(find.textContaining('TODAY'), findsOneWidget);
    expect(find.text('Market day'), findsOneWidget);
    double y(String key) => tester.getTopLeft(find.byKey(Key(key))).dy;
    expect(y('panel-tasks'), lessThan(y('panel-reminders')));
    expect(y('panel-reminders'), lessThan(y('panel-routines')));
    final late = find.byKey(const Key('ptask-late'));
    expect(find.descendant(of: late, matching: find.text('Late')), findsOneWidget);
    expect(find.descendant(of: late, matching: find.text('Gela · Club')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('ptask-timed')), matching: find.text('18:30')),
        findsOneWidget);
    final ping = find.byKey(const Key('premind-ping'));
    expect(find.descendant(of: ping, matching: find.text('09:00')), findsOneWidget);
    expect(find.descendant(of: ping, matching: find.text('Club')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('routine-r1')), matching: find.text('Gela')),
        findsOneWidget);
    await tester.tap(find.text('Title ping'));
    expect(opened, 'ping');
  });

  testWidgets('an empty day says so, and hides the empty sections', (tester) async {
    await tester.pumpWidget(host(DayPanel(
      day: today,
      today: DateTime.utc(2026, 10, 24),
      plan: const DayPlan(),
      notes: const [],
      onAddNote: () {},
    )));
    expect(find.text('Nothing on this day.'), findsOneWidget);
    expect(find.byKey(const Key('panel-tasks')), findsNothing);
    expect(find.textContaining('TODAY'), findsNothing);
  });

  testWidgets('one line explains the marks', (tester) async {
    await tester.pumpWidget(host(const CalendarLegend()));
    for (final word in ['Task', 'Done', 'Reminder', 'Routine', 'By a bot']) {
      expect(find.text(word), findsOneWidget);
    }
  });

  testWidgets('the Workspace calendar: markers in the grid, the day in the panel', (tester) async {
    final day = isoDay(appToday());
    final parts = day.split('-').map(int.parse).toList();
    await pumpWorkspace(tester, const WorkspaceScreen(), <String>[], size: tall, extra: (o) {
      final path = '${o.method} ${o.uri.path}';
      if (path == 'GET /api/tasks' && o.uri.queryParameters.containsKey('from')) {
        return FakeAdapter.json([
          {...wtask('t1', 'Pay rent', project: 'p1', due: '${day}T10:00:00+01:00'), 'created_by_bot': 'b1'},
        ]);
      }
      if (path == 'GET /api/routines/occurrences') {
        return FakeAdapter.json({'occurrences': [occ('r1', day, '09:00')], 'truncated': false});
      }
      return richAnswer(o);
    });
    await tapKey(tester, 'layout-menu');
    await tester.tap(find.text('Calendar'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('calendar-legend')), findsOneWidget);
    expect(find.byKey(const Key('dot-t1')), findsOneWidget);
    expect(find.byKey(Key('repeat-$day')), findsOneWidget);
    // today is picked: the panel, not the grid, names the task
    expect(find.text('Pay rent'), findsOneWidget);
    await tapKey(tester, 'day-${parts[0]}-${parts[1]}-${parts[2]}');
    final row = find.byKey(const Key('ptask-t1'));
    expect(find.descendant(of: row, matching: find.text('Pay rent')), findsOneWidget);
    expect(find.descendant(of: row, matching: find.text('Club')), findsOneWidget);
    expect(find.byKey(const Key('panel-routines')), findsOneWidget);
    expect(find.byKey(const Key('routine-r1')), findsOneWidget);
  });
}
