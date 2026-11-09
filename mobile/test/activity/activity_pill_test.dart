import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/activity_pill.dart';
import 'package:roost_mobile/features/chat/chat_flow.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/features/chat/run_steps.dart';
import 'package:roost_mobile/features/chat/working_timer.dart';
import 'package:roost_mobile/theme/app_theme.dart';

import '../fake_adapter.dart';

Widget host(Widget child, {bool still = false}) => ProviderScope(
      child: MaterialApp(
        theme: buildTheme(),
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(disableAnimations: still),
            child: Scaffold(body: ListView(children: [child])),
          ),
        ),
      ),
    );

ActivityRun run({bool done = false}) {
  var r = const ActivityRun.empty(runId: 'r1', botId: 'b1', threadId: 't1');
  r = r.withStep(const RunStep(
      step: 1, kind: 'search', line: 'Browsing web.whatsapp.com', at: '2026-10-23T20:15:00Z'));
  r = r.withStep(const RunStep(
      step: 2, kind: 'program', line: 'Running a program', at: '2026-10-23T20:15:30Z'));
  return done ? r.finished('2026-10-23T20:15:42Z') : r;
}

const note = FlowNote(
    kind: 'program',
    line: 'Ran a program',
    at: '2026-10-23T20:15:31Z',
    raw: 'Ran: curl -sI https://web.whatsapp.com · exit 0');

void main() {
  testWidgets('the pill says what it does, with one ellipsis while it works', (tester) async {
    await tester.pumpWidget(host(const ActivityPill(kind: 'search', line: 'Browsing web.whatsapp.com')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Browsing web.whatsapp.com…'), findsOneWidget);
    await tester.pumpWidget(host(const ActivityPill(kind: 'think', line: 'Thinking…')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Thinking…'), findsOneWidget);
  });

  testWidgets('working with no step yet: its own robot, its words and a timer, never On it', (tester) async {
    final busy = Bot.fromJson({'id': 'b1', 'name': 'Gela', 'status': 'on_it', 'activity': 'opening WhatsApp Web'});
    await tester.pumpWidget(host(LiveBotPill(bot: busy)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('working-bot')), findsOneWidget);
    expect(find.text('Opening WhatsApp Web…'), findsOneWidget);
    expect(find.byKey(const Key('working-timer')), findsOneWidget);
    expect(find.textContaining('On it'), findsNothing);
    final quiet = Bot.fromJson({'id': 'b1', 'name': 'Gela', 'status': 'on_it'});
    await tester.pumpWidget(host(LiveBotPill(bot: quiet)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Reading your message…'), findsOneWidget);
    await tester.pumpWidget(host(LiveBotPill(bot: quiet, words: 'checking your week.')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Checking your week…'), findsOneWidget);
    await tester.pumpWidget(host(const SizedBox()));
  });

  testWidgets('the timer counts the seconds', (tester) async {
    final since = DateTime.now().subtract(const Duration(seconds: 12));
    await tester.pumpWidget(host(WorkingTimer(since: since)));
    expect(find.text('12s'), findsOneWidget);
    await tester.pumpWidget(host(const SizedBox()));
  });

  testWidgets('a live run shows the pill with its newest step', (tester) async {
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: run()))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('activity-live')), findsOneWidget);
    expect(find.text('Running a program…'), findsOneWidget);
  });

  testWidgets('a live run with its bot shows the bot\'s robot instead of an icon', (tester) async {
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: run()), avatar: const Avatar())));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const Key('working-bot')), findsOneWidget);
    expect(find.byKey(const Key('working-timer')), findsOneWidget);
    await tester.pumpWidget(host(const SizedBox()));
  });

  testWidgets('a finished run is one line; its sheet shows plain steps and hides the code until asked',
      (tester) async {
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: run(done: true), notes: const [note]))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Worked for 42 s · 3 steps'), findsOneWidget);
    await tester.tap(find.byKey(const Key('activity-done')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity-sheet')), findsOneWidget);
    expect(find.text('Browsing web.whatsapp.com'), findsOneWidget);
    expect(find.text('Ran a program'), findsOneWidget);
    expect(find.textContaining('curl'), findsNothing);
    await tester.tap(find.text('Technical details'));
    await tester.pumpAndSettle();
    expect(find.textContaining('curl'), findsOneWidget);
  });

  testWidgets('a live run says the bot\'s newest note', (tester) async {
    final r = run().withStep(const RunStep(
        step: 3, kind: 'note', line: 'Picking the Acme job.', at: '2026-10-23T20:15:31Z', state: 'done'));
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: r))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining('Picking the Acme job'), findsOneWidget);
  });

  testWidgets('the sheet lists notes among the steps, quietly, with the Web mark on a tainted one', (tester) async {
    var r = const ActivityRun.empty(runId: 'r1', botId: 'b1', threadId: 't1');
    r = r.withStep(const RunStep(
        step: 1, kind: 'note', line: 'First a fresh search.', at: '2026-10-23T20:15:00Z', state: 'done'));
    r = r.withStep(const RunStep(
        step: 2, kind: 'search', line: 'Searched the web', at: '2026-10-23T20:15:02Z', state: 'done'));
    r = r.withStep(const RunStep(
        step: 3, kind: 'note', line: 'Found the job.', at: '2026-10-23T20:15:10Z', state: 'done', tainted: true));
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: r.finished('2026-10-23T20:15:12Z')))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Worked for 12 s · 1 step'), findsOneWidget);
    await tester.tap(find.text('Worked for 12 s · 1 step'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('run-note')), findsNWidgets(2));
    expect(find.text('First a fresh search.'), findsOneWidget);
    expect(find.text('Found the job.'), findsOneWidget);
    expect(find.byKey(const Key('web-mark')), findsOneWidget);
  });

  testWidgets('with less motion everything stands still and settles', (tester) async {
    await tester.pumpWidget(host(ActivityItemView(item: ActivityItem(run: run())), still: true));
    await tester.pumpAndSettle();
    expect(find.text('Running a program…'), findsOneWidget);
  });

  testWidgets('in a real chat the raw lines are gone and one quiet line stands for them', (tester) async {
    Map<String, Object?> msg(String id, String role, String body, int seq, {String kind = 'text'}) => {
          'id': id,
          'thread_id': 't1',
          'role': role,
          'body': body,
          'tainted': false,
          'seq': seq,
          'created_at': '2026-10-23T20:15:${seq.toString().padLeft(2, '0')}Z',
          'kind': kind,
          'author_bot_id': role == 'bot' ? 'b1' : null,
        };
    final adapter = FakeAdapter((o) {
      if (o.path == '/api/bots/b1/chat') return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
      return FakeAdapter.json([
        msg('u1', 'user', 'open whatsapp web', 1),
        msg('b1', 'bot', 'On it: opening WhatsApp Web in my browser.', 2),
        msg('p1', 'system',
            jsonEncode({'op': 'run', 'command': 'curl -sI https://web.whatsapp.com', 'exit_code': 0, 'output': 'HTTP/2 200'}),
            3, kind: 'program_activity'),
        msg('ans', 'user', 'Yes: Run a program: curl', 4, kind: 'card_answer'),
        msg('b2', 'bot', 'Continuing: opening WhatsApp Web in my browser.', 5),
        msg('b3', 'bot', 'WhatsApp Web is open. Scan the QR code.', 6),
      ]);
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(theme: buildTheme(), home: const ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ran:'), findsNothing);
    expect(find.textContaining('curl'), findsNothing);
    expect(find.textContaining('Continuing'), findsNothing);
    expect(find.textContaining('On it:'), findsNothing);
    expect(find.text('Output'), findsNothing);
    expect(find.text('Worked · 1 step'), findsOneWidget);
    expect(find.text('WhatsApp Web is open. Scan the QR code.'), findsOneWidget);
  });
}
