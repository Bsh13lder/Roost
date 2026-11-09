import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_dates.dart';
import 'package:roost_mobile/workspace/workspace_screen.dart';

import '../fake_adapter.dart';
import 'workspace_fakes.dart';

/// A small stand-in for the server's reading: "friday", "!high" and "*"
/// are read unless kept; a line naming no day takes `default_due`.
Map<String, Object?> echoReading(Map<String, dynamic> body) {
  final text = body['text'] as String;
  final keep = [for (final k in (body['keep'] as List? ?? const [])) '$k'];
  final skip = [for (final k in (body['skip'] as List? ?? const [])) '$k'];
  bool reads(String w) => text.contains(w) && !keep.contains(w);
  final friday = reads('friday');
  final high = reads('!high');
  final star = text.contains('*') && !skip.contains('star');
  final due = friday
      ? '2026-10-23T09:00:00+02:00'
      : body['default_due'] as String?;
  final title = [
    for (final w in text.split(' '))
      if (w.isNotEmpty && !(friday && w == 'friday') && !(high && w == '!high') && w != '*') w,
  ].join(' ');
  return {
    'title': title,
    'ready': title.isNotEmpty,
    'due_date': due,
    'due_text': friday ? 'Fri 23 Oct 09:00' : (due == null ? null : 'that day'),
    'priority': high ? 'high' : null,
    'starred': star,
    'tags': <String>[],
    'matches': {
      if (friday) 'date': ['friday'],
      if (high) 'priority': ['!high'],
    },
  };
}

FakeReply? quickAnswer(RequestOptions o) {
  if (o.method == 'POST' && o.uri.path == '/api/tasks/parse') {
    return FakeAdapter.json(echoReading((o.data as Map).cast<String, dynamic>()));
  }
  if (o.method == 'GET' && o.uri.path == '/api/tasks' && o.uri.query.contains('status=all')) {
    return FakeAdapter.json([
      {...wtask('t5', 'Milk'), 'tags': ['shopping']},
    ]);
  }
  return null;
}

Map<String, dynamic> lastBody(FakeAdapter a, String path) =>
    (a.requests.lastWhere((r) => r.method == 'POST' && r.uri.path == path).data as Map)
        .cast<String, dynamic>();

String barText(WidgetTester tester) =>
    tester.widget<TextField>(find.byKey(const Key('work-bar'))).controller!.text;

Future<void> typeLine(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(const Key('work-bar')), text);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

/// Picker buttons sit in a row that scrolls on a narrow phone.
Future<void> tapPick(WidgetTester tester, String id) async {
  final f = find.byKey(Key('qp-$id'));
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

Future<void> submit(WidgetTester tester) async {
  await tester.testTextInput.receiveAction(TextInputAction.done);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('on the Calendar, a line with no day is due on the chosen day',
      (tester) async {
    final calls = <String>[];
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), calls, extra: quickAnswer);
    await tester.tap(find.byKey(const Key('section-calendar')));
    await tester.pumpAndSettle();
    final today = appToday();
    final next = today.add(const Duration(days: 1));
    final day = next.month == today.month ? next : today.subtract(const Duration(days: 1));
    await tester.tap(find.byKey(Key('day-${day.year}-${day.month}-${day.day}')));
    await tester.pumpAndSettle();

    await typeLine(tester, 'Call Ana');
    final badge = find.byKey(const Key('chip-day-badge'));
    expect(badge, findsOneWidget);
    expect(find.descendant(of: badge, matching: find.textContaining('Due ')), findsOneWidget);
    expect(lastBody(a, '/api/tasks/parse')['default_due'], isoDay(day));
    await submit(tester);
    expect(lastBody(a, '/api/tasks'), {'title': 'Call Ana', 'due_date': isoDay(day)});
  });

  testWidgets('on the Calendar, a line that names a day keeps its own day',
      (tester) async {
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await tester.tap(find.byKey(const Key('section-calendar')));
    await tester.pumpAndSettle();
    await typeLine(tester, 'Call Ana friday');
    expect(find.byKey(const Key('chip-day-badge')), findsNothing);
    expect(find.text('Due Fri 23 Oct 09:00'), findsOneWidget);
    await submit(tester);
    expect(lastBody(a, '/api/tasks')['due_date'], '2026-10-23T09:00:00+02:00');
  });

  testWidgets('on Tasks, the line carries no default day', (tester) async {
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'Call Ana');
    expect(lastBody(a, '/api/tasks/parse').containsKey('default_due'), isFalse);
    expect(find.byKey(const Key('chip-day-badge')), findsNothing);
  });

  testWidgets('suggestions finish /project, #tag and !priority on tap',
      (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'Pay /C');
    await tester.tap(find.byKey(const Key('suggest-Club')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Pay /Club ');

    await typeLine(tester, 'Milk #sh');
    await tester.tap(find.byKey(const Key('suggest-shopping')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Milk #shopping ');

    await typeLine(tester, 'Rent !h');
    expect(find.byKey(const Key('suggest-high')), findsOneWidget);
    await tester.tap(find.byKey(const Key('suggest-high')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Rent !high ');
    expect(find.byKey(const Key('suggest-strip')), findsNothing);
  });

  testWidgets('the picker buttons write the same words typing would',
      (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'Pay rent');
    await tapPick(tester, 'priority');
    await tester.tap(find.byKey(const Key('choice-urgent')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Pay rent !urgent');

    await tapPick(tester, 'project');
    await tester.tap(find.byKey(const Key('project-Club')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Pay rent !urgent /Club');

    await tapPick(tester, 'date');
    await tester.tap(find.byKey(const Key('pick-Tomorrow')));
    await tester.pumpAndSettle();
    final tomorrow = isoDay(appToday().add(const Duration(days: 1)));
    expect(barText(tester), 'Pay rent !urgent /Club $tomorrow');

    await tapPick(tester, 'repeat');
    await tester.tap(find.byKey(const Key('choice-week')));
    await tester.pumpAndSettle();
    expect(barText(tester), 'Pay rent !urgent /Club $tomorrow every week');
  });

  testWidgets("a chip's x keeps its words in the title, or skips its kind",
      (tester) async {
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'Pay rent !high *');
    expect(find.byKey(const Key('chip-priority')), findsOneWidget);
    await tester.tap(find.byKey(const Key('chip-remove-priority')));
    await tester.pump();
    expect(find.byKey(const Key('chip-priority')), findsNothing);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(lastBody(a, '/api/tasks/parse')['keep'], ['!high']);
    expect(find.text('Pay rent !high'), findsOneWidget);

    await tester.tap(find.byKey(const Key('chip-remove-star')));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(lastBody(a, '/api/tasks/parse')['skip'], ['star']);
    expect(find.byKey(const Key('chip-star')), findsNothing);
    await submit(tester);
    expect(lastBody(a, '/api/tasks'), {'title': 'Pay rent !high'});
  });

  testWidgets('Remind me rides into the new task with no advance reminder',
      (tester) async {
    final a = await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'Call Ana friday');
    await tapPick(tester, 'remind');
    await tester.tap(find.byKey(const Key('remind-1 hour before')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chip-picked-reminder')), findsOneWidget);
    expect(find.text('Remind Fri 23 Oct, 08:00'), findsOneWidget);
    await submit(tester);
    expect(lastBody(a, '/api/tasks'), {
      'title': 'Call Ana',
      'due_date': '2026-10-23T09:00:00+02:00',
      'reminder_at': '2026-10-23T08:00',
      'pre_reminders': <String>[],
    });
    expect(find.byKey(const Key('chip-picked-reminder')), findsNothing);
  });

  testWidgets('the ? opens the quick line help', (tester) async {
    await pumpWorkspace(tester, const WorkspaceScreen(), [], extra: quickAnswer);
    await typeLine(tester, 'x');
    await tapPick(tester, 'help');
    expect(find.text('Quick line help'), findsOneWidget);
    expect(find.text('tomorrow at 9'), findsOneWidget);
  });
}
