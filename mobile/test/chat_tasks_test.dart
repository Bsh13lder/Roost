import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/board/tasks/reschedule_sheet.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';
import 'package:roost_mobile/chat/cards/card_base.dart';
import 'package:roost_mobile/chat/cards/reminder_card.dart';
import 'package:roost_mobile/chat/cards/report_bubble.dart';
import 'package:roost_mobile/chat/cards/task_cards.dart';
import 'package:roost_mobile/chat/mentions.dart';
import 'package:roost_mobile/chat/project_tokens.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/message_view.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

Map<String, dynamic> task(String id, String title,
        {String status = 'todo', String? project, bool tainted = false}) =>
    {
      'id': id,
      'title': title,
      'status': status,
      'priority': 'urgent',
      'due_date': null,
      'reminder_at': '2026-10-26T08:00:00+00:00',
      'project_id': project,
      'tainted': tainted,
      'due_bucket': 'none',
    };

const projects = [
  {'id': 'p1', 'name': 'Casa Nueva', 'currency': 'EUR'}
];

/// Answers the task list by id, the projects, every POST with [post] and
/// every PUT (a reminder's answer) with [put].
FakeHandler tasksHandler(List<Map<String, dynamic>> tasks,
        {FakeReply Function(RequestOptions o)? post,
        FakeReply Function(RequestOptions o)? put}) =>
    (o) {
      if (o.method == 'POST' || o.method == 'PATCH') {
        return post?.call(o) ?? FakeAdapter.json({});
      }
      if (o.method == 'PUT') return put?.call(o) ?? FakeAdapter.json({});
      if (o.uri.path == '/api/projects') return FakeAdapter.json(projects);
      return FakeAdapter.json(tasks);
    };

Message reminder(String? taskId, [Map<String, dynamic> answer = const {}]) =>
    cardMessage(
        'report',
        jsonEncode({
          'source': 'reminder',
          'headline': 'Reminder: Fix the sink',
          'text': 'Quick reminder: Fix the sink is due today.',
          'tainted': false,
          'task_id': taskId,
          ...answer,
        }));

const answerPath = '/api/threads/t1/messages/m-report/reminder-answer';

Map<String, dynamic> answerSent(FakeAdapter adapter) {
  final put = adapter.requests.where((r) => r.method == 'PUT').single;
  expect(put.path, answerPath);
  final data = put.data;
  return (data is String ? jsonDecode(data) : data) as Map<String, dynamic>;
}

void main() {
  test('# opens only at a word start and picking writes #Name', () {
    expect(mentionQuery('tasks in #Ca', mentionProject), 'Ca');
    expect(mentionQuery('issue a#1', mentionProject), isNull);
    expect(mentionQuery('tasks in #Ca'), isNull);
    final next = insertMention('show #ca', 8, 'Casa Nueva', mentionProject);
    expect(next.text, 'show #Casa Nueva ');
    expect(next.caret, 17);
  });

  test('#Name tokens are read exactly, longest first, never inside a word', () {
    const opts = [MentionOption('p1', 'Casa'), MentionOption('p2', 'Casa Nueva')];
    final parts = splitProjectTokens('left in #casa nueva and x#Casa?', opts);
    expect([for (final p in parts) p.text], ['left in ', '#casa nueva', ' and x#Casa?']);
    expect(parts[1].project?.id, 'p2');
    expect(splitProjectTokens('#Casas', opts).single.project, isNull);
  });

  test('a task_cards body is read field by field', () {
    final d = parseTaskCards('{"task_ids":["a",3],"verb":"odd","more":-2}');
    expect(d?.ids, ['a']);
    expect(d?.verb, 'tasks');
    expect(d?.more, 0);
    expect(parseTaskCards('{"task_ids":[]}'), isNull);
    expect(parseTaskCards('nope'), isNull);
  });

  testWidgets('task cards draw the tasks and a tick finishes one',
      (tester) async {
    final adapter = await pumpCard(
        tester,
        cardMessage('task_cards', '{"task_ids":["t1"],"verb":"listed","more":2}'),
        tasksHandler([task('t1', 'Fix the sink', project: 'p1', tainted: true)]));
    expect(find.text('Your tasks'), findsOneWidget);
    expect(find.text('Fix the sink'), findsOneWidget);
    expect(find.text('Casa Nueva'), findsOneWidget);
    expect(find.text('Urgent'), findsOneWidget);
    expect(find.byKey(const Key('web-mark')), findsOneWidget);
    expect(find.text('and 2 more on the Board'), findsOneWidget);
    final listed = adapter.requests.firstWhere((r) => r.uri.path == '/api/tasks');
    expect(listed.uri.queryParameters['ids'], 't1');
    await tester.tap(find.byKey(const Key('task-tick-t1')));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST').single.path,
        '/api/tasks/t1/complete');
  });

  testWidgets('a long card shows five tasks and folds the rest', (tester) async {
    final ids = [for (var i = 1; i <= 7; i++) 't$i'];
    await pumpCard(
        tester,
        cardMessage('task_cards', jsonEncode({'task_ids': ids, 'verb': 'listed'})),
        tasksHandler([for (final id in ids) task(id, 'Task $id')]));
    expect(find.text('Task t5'), findsOneWidget);
    expect(find.text('Task t6'), findsNothing);
    await tester.tap(find.text('Show 2 more'));
    await tester.pumpAndSettle();
    expect(find.text('Task t7'), findsOneWidget);
    await tester.tap(find.text('Show less'));
    await tester.pumpAndSettle();
    expect(find.text('Task t6'), findsNothing);
  });

  testWidgets('five tasks or fewer need no toggle', (tester) async {
    final ids = [for (var i = 1; i <= 5; i++) 't$i'];
    await pumpCard(
        tester,
        cardMessage('task_cards', jsonEncode({'task_ids': ids, 'verb': 'listed'})),
        tasksHandler([for (final id in ids) task(id, 'Task $id')]));
    expect(find.text('Task t5'), findsOneWidget);
    expect(find.textContaining('Show'), findsNothing);
  });

  testWidgets('gone tasks say so', (tester) async {
    await pumpCard(tester,
        cardMessage('task_cards', '{"task_ids":["t9"],"verb":"added"}'), tasksHandler([]));
    expect(find.text('Added a task'), findsOneWidget);
    expect(find.text(tasksGoneText), findsOneWidget);
  });

  testWidgets(
      'a reminder is the bot\'s own words, a quiet footer and four chips; Done says so',
      (tester) async {
    final adapter = await pumpCard(
        tester, reminder('t1'), tasksHandler([task('t1', 'Fix the sink')]));
    expect(find.text('Quick reminder: Fix the sink is due today.'), findsOneWidget);
    expect(find.text(reminderFoot), findsOneWidget);
    expect(find.byType(CardFrame), findsNothing);
    expect(find.byKey(const Key('reminder-chips')), findsOneWidget);
    for (final label in ['Done', 'Failed', 'Reschedule', 'Skip']) {
      expect(find.text(label), findsOneWidget);
    }
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST').single.path,
        '/api/tasks/t1/complete');
    expect(find.text(reminderDone), findsOneWidget);
    expect(find.text('Failed'), findsNothing);
    expect(answerSent(adapter), {'answer': 'done', 'due': null});
  });

  testWidgets('Failed marks it failed', (tester) async {
    final adapter = await pumpCard(
        tester, reminder('t1'), tasksHandler([task('t1', 'Fix the sink')]));
    await tester.tap(find.text('Failed'));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST').single.path,
        '/api/tasks/t1/fail');
    expect(find.text(reminderFailed), findsOneWidget);
    expect(answerSent(adapter), {'answer': 'failed', 'due': null});
  });

  testWidgets('Skip is kept on the server and changes no task', (tester) async {
    final skipping = await pumpCard(
        tester, reminder('t2'), tasksHandler([task('t2', 'Water plants')]));
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    expect(find.text(reminderSkipped), findsOneWidget);
    expect(skipping.requests.where((r) => r.method == 'POST'), isEmpty);
    expect(answerSent(skipping), {'answer': 'skipped', 'due': null});
  });

  testWidgets('a kept answer folds the card after a restart', (tester) async {
    await pumpCard(tester, reminder('t2', {'answer': 'skipped'}),
        tasksHandler([task('t2', 'Water plants')]));
    expect(find.text(reminderSkipped), findsOneWidget);
    expect(find.text('Skip'), findsNothing);
    expect(find.text('Done'), findsNothing);
  });

  testWidgets('a kept Reschedule says where it moved', (tester) async {
    await pumpCard(tester, reminder('t2', {'answer': 'rescheduled', 'answer_due': null}),
        tasksHandler([task('t2', 'Water plants')]));
    expect(find.text('Now has no date'), findsOneWidget);
    expect(find.text('Reschedule'), findsNothing);
  });

  testWidgets('a Skip the server refused keeps the buttons and says why',
      (tester) async {
    await pumpCard(
        tester,
        reminder('t2'),
        tasksHandler([task('t2', 'Water plants')],
            put: (_) => FakeAdapter.json({'detail': 'Message not found'}, status: 404)));
    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();
    expect(find.text(reminderSkipped), findsNothing);
    expect(find.text("That wasn't found."), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
  });

  test('a kept answer in the card\'s words', () {
    expect(answerWords('done', null), reminderDone);
    expect(answerWords('failed', null), reminderFailed);
    expect(answerWords('skipped', null), reminderSkipped);
    expect(answerWords('rescheduled', null), 'Now has no date');
    expect(answerWords('rescheduled', '2026-10-29T10:00'), startsWith('Moved to '));
    expect(answerWords('later', null), isNull);
    expect(answerWords(null, null), isNull);
  });

  testWidgets('a deleted task says it is gone, before or after a button',
      (tester) async {
    await pumpCard(tester, reminder('t1'), tasksHandler([]));
    expect(find.text(taskGoneText), findsOneWidget);
  });

  testWidgets('a task deleted meanwhile says it is gone after Done', (tester) async {
    await pumpCard(
        tester,
        reminder('t1'),
        tasksHandler([task('t1', 'Fix the sink')],
            post: (_) => FakeAdapter.json({'detail': 'No open task with that id'},
                status: 404)));
    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();
    expect(find.text(taskGoneText), findsOneWidget);
  });

  testWidgets('a done task says Done; a reminder with no task stays a report',
      (tester) async {
    await pumpCard(tester, reminder('t1'),
        tasksHandler([task('t1', 'Fix the sink', status: 'done')]));
    expect(find.text(reminderDone), findsOneWidget);
  });

  testWidgets('a reminder with no task is a plain bubble with no chips', (tester) async {
    await pumpCard(tester, reminder(null), tasksHandler([]));
    expect(find.text('Quick reminder: Fix the sink is due today.'), findsOneWidget);
    expect(find.text(reminderFoot), findsOneWidget);
    expect(find.byKey(const Key('reminder-chips')), findsNothing);
    expect(find.textContaining('Report:'), findsNothing);
  });

  test('a reschedule keeps the task time and says where it moved', () {
    const t = TaskItem(
        id: 't', title: 'x', status: 'todo', priority: 'medium',
        dueDate: '2026-10-16T09:00:00+02:00');
    final c = withOwnTime(t, RescheduleChoice(DateTime.utc(2026, 10, 29)));
    expect(c.wire, '2026-10-29T09:00');
    expect(movedWords(const RescheduleChoice(null)), 'Now has no date');
    expect(movedWords(c), startsWith('Moved to '));
  });

  Future<void> pumpView(WidgetTester tester, Message m) async {
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(FakeAdapter(tasksHandler([]))),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(home: Scaffold(body: MessageView(message: m, text: m.body))),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('your #Project is a chip in your bubble', (tester) async {
    await pumpView(
        tester,
        const Message(
            id: 'u1', threadId: 't1', role: 'user', body: 'left in #casa nueva?',
            seq: 2, createdAt: '2026-10-26T10:00:00+00:00', kind: 'text'));
    expect(find.byKey(const Key('project-chip-p1')), findsOneWidget);
    expect(find.text('Casa Nueva'), findsOneWidget);
  });

  testWidgets('a web-made reply wears the quiet Web mark under its text',
      (tester) async {
    await pumpView(
        tester,
        const Message(
            id: 'b1', threadId: 't1', role: 'bot', body: 'From the page.',
            seq: 3, createdAt: '2026-10-26T10:00:00+00:00', kind: 'text',
            tainted: true));
    expect(find.byKey(const Key('web-mark')), findsOneWidget);
    expect(find.text('from web content'), findsNothing);
    final text = tester.getTopLeft(find.text('From the page.'));
    final mark = tester.getTopLeft(find.byKey(const Key('web-mark')));
    expect(mark.dy, greaterThan(text.dy));
  });
}
