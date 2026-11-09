import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/computer/computer_screen.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'computer_steps_test.dart' show step;
import 'fake_adapter.dart';
import 'fake_socket.dart';

/// The chat with a bot, its sockets recorded in [sockets] by URI.
class Harness {
  final sockets = <Uri, List<FakeSocket>>{};
  late final ProviderContainer container;
  late final FakeAdapter adapter;

  List<FakeSocket> get live => [
    for (final e in sockets.entries)
      if (e.key.path == '/api/bots/b1/live') ...e.value,
  ];

  Future<void> pump(WidgetTester tester, {bool reduceMotion = true}) async {
    tester.view
      ..physicalSize =
          const Size(1080, 2400) // a phone: 360 x 800
      ..devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    adapter = FakeAdapter((o) {
      if (o.path == '/api/bots/b1/chat') {
        return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
      }
      if (o.path == '/api/threads/t1/messages') {
        return FakeAdapter.json([
          {
            'id': 'u1',
            'thread_id': 't1',
            'role': 'user',
            'body': 'Check my Upwork messages',
            'seq': 1,
            'created_at': '2026-10-23T11:59:00Z',
            'kind': 'text',
          },
        ]);
      }
      return FakeAdapter.json({});
    });
    container = ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(MemorySessionStore()),
        httpAdapterProvider.overrideWithValue(adapter),
        socketOpenerProvider.overrideWithValue((uri, headers) {
          final socket = FakeSocket();
          (sockets[uri] ??= []).add(socket);
          return socket;
        }),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(disableAnimations: reduceMotion),
            child: child!,
          ),
          home: const ChatScreen(botId: 'b1'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    // After the saved session loads: the live state starts afresh then.
    container.read(liveProvider.notifier).seed([
      Bot.fromJson({
        'id': 'b1',
        'name': 'Chief',
        'status': 'on_it',
        'avatar': {'shape': 'mochi', 'color': '#6c5ce0'},
      }),
    ]);
    await tester.pump();
  }

  Future<void> frame(WidgetTester tester, Map<String, dynamic> f) async {
    container.read(frameBusProvider).add(f);
    await tester.pump();
    await tester.pump();
  }
}

/// The full screen spins while it connects, so it never settles: let the
/// page slide in and its first requests answer.
Future<void> _settleScreen(WidgetTester tester) async {
  for (var i = 0; i < 10; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

const _resting = {'type': 'bot_status', 'bot_id': 'b1', 'status': 'resting'};

// Owner, 2026-10-26: the chat never shows the screen and never opens its
// socket; the screen lives on the bot's computer screen.
void main() {
  testWidgets('a step shows one compact line: the site, the step, its number', (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester);
    expect(find.byKey(const Key('computer-card')), findsNothing);

    await h.frame(tester, step(1, kind: 'look', line: 'Looked at the page'));
    await h.frame(tester, step(2, line: 'Clicked Messages'));

    final card = find.byKey(const Key('computer-card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(of: card, matching: find.text('upwork.com')),
      findsOneWidget,
    );
    expect(find.text('Clicked Messages'), findsOneWidget);
    expect(find.text('Step 2'), findsOneWidget);
    expect(find.text('Live'), findsNothing);
    expect(h.live, isEmpty);
    // One line, not a screen card.
    expect(tester.getSize(card).height, lessThan(60));
  });

  testWidgets('the end of the run folds to the quiet line, newest included', (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, step(1));
    await h.frame(tester, step(2));
    await h.frame(tester, _resting);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('computer-card')), findsNothing);
    expect(find.byKey(const Key('computer-kept')), findsNothing);
    expect(find.byKey(const Key('computer-done')), findsOneWidget);
    expect(
      find.text('Used its computer · upwork.com · 2 steps'),
      findsOneWidget,
    );
    expect(h.live, isEmpty);
  });

  testWidgets('every finished run is a line; no screen opens', (tester) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, step(1, run: 'r1', line: 'Opened WhatsApp'));
    await h.frame(tester, _resting);
    await h.frame(
      tester,
      step(1, run: 'r2', line: 'Showed the QR', at: '2026-10-23T12:05:00Z'),
    );
    await h.frame(tester, _resting);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('computer-done')), findsNWidgets(2));
    expect(find.byKey(const Key('computer-kept')), findsNothing);
    expect(h.live, isEmpty);
  });

  testWidgets('tapping the line opens the steps, with no screen in the sheet', (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, step(1, kind: 'look', line: 'Looked at the page'));
    await h.frame(tester, step(2, line: 'Clicked Messages'));

    await tester.tap(find.byKey(const Key('computer-card')));
    await tester.pumpAndSettle();

    final sheet = find.byKey(const Key('computer-sheet'));
    expect(sheet, findsOneWidget);
    expect(
      find.descendant(of: sheet, matching: find.text('Chief')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: sheet, matching: find.text('Looked at the page')),
      findsOneWidget,
    );
    expect(find.text('Take control'), findsOneWidget);
    expect(find.text('Open computer'), findsOneWidget);
    expect(find.byKey(const Key('computer-big-screen')), findsNothing);
    expect(h.live, isEmpty);

    await h.frame(tester, step(3, kind: 'type', line: 'Typed a search'));
    expect(
      find.descendant(of: sheet, matching: find.text('Typed a search')),
      findsOneWidget,
    );
  });

  testWidgets('the done line opens the same steps', (tester) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, step(1, line: 'Clicked Messages'));
    await h.frame(tester, _resting);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('computer-done')));
    await tester.pumpAndSettle();
    final sheet = find.byKey(const Key('computer-sheet'));
    expect(
      find.descendant(of: sheet, matching: find.text('Clicked Messages')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('computer-big-screen')), findsNothing);
  });

  testWidgets("the sheet's Open computer goes to the bot's computer screen", (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, step(1, line: 'Showed the QR'));
    await h.frame(tester, _resting);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('computer-done')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open computer'));
    await _settleScreen(tester);

    expect(find.byKey(const Key('computer-sheet')), findsNothing);
    expect(find.byType(ComputerScreen), findsOneWidget);
    // Only the computer screen opens the live view.
    expect(h.live, hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a finished run with its own steps is just its line', (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, {
      ...step(1, line: 'Opened WhatsApp'),
      'type': 'run_step',
      'kind': 'computer',
      'state': 'done',
    });
    await h.frame(tester, step(1, line: 'Showed the QR'));
    await h.frame(tester, _resting);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('activity-done')), findsOneWidget);
    expect(find.byKey(const Key('computer-kept')), findsNothing);
    expect(h.live, isEmpty);

    // Its steps sheet goes to the computer screen the same way.
    await tester.tap(find.byKey(const Key('activity-done')));
    await tester.pumpAndSettle();
    expect(h.live, isEmpty);
    await tester.tap(find.byKey(const Key('activity-open-computer')));
    await _settleScreen(tester);
    expect(find.byType(ComputerScreen), findsOneWidget);
    expect(h.live, hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('with motion on, the line animates and still shows its step', (
    tester,
  ) async {
    final h = Harness();
    await h.pump(tester, reduceMotion: false);
    await h.frame(tester, step(1, line: 'Clicked Messages'));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Clicked Messages'), findsOneWidget);
    expect(h.live, isEmpty);
    // Leave the screen so the repeating shimmer stops before the test ends.
    await tester.pumpWidget(const SizedBox());
  });
}
