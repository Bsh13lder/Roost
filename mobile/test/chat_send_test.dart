import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';

import 'fake_adapter.dart';

Map<String, Object?> msg(String id, String role, String body, int seq) => {
      'id': id,
      'thread_id': 't1',
      'role': role,
      'body': body,
      'tainted': false,
      'seq': seq,
      'created_at': '2026-10-22T12:19:00+00:00',
      'kind': 'text',
      'author_bot_id': role == 'bot' ? 'b1' : null,
    };

void main() {
  testWidgets('sends a message and shows it; queued shows the quiet line',
      (tester) async {
    final adapter = FakeAdapter((o) {
      if (o.path == '/api/bots/b1/chat') {
        return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
      }
      if (o.path == '/api/threads/t1/messages' && o.method == 'GET') {
        return FakeAdapter.json([msg('m1', 'bot', 'Hello **there**', 1)]);
      }
      if (o.path == '/api/threads/t1/messages' && o.method == 'POST') {
        expect(o.data, {'text': 'Do the thing'});
        return FakeAdapter.json({
          'message_id': 'm2',
          'status': 'queued',
          'queued': true,
          'mentioned': <String>[],
        });
      }
      fail('unexpected ${o.method} ${o.path}');
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);

    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('Hello'), findsOneWidget);
    expect(find.text('14:19'), findsOneWidget); // 12:19 UTC, CEST

    await tester.enterText(find.byKey(const Key('composer')), 'Do the thing');
    // The empty box shows Call (voice is assumed until the server says no);
    // the typed text turns it into Send on the next frame.
    await tester.pump();
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();

    expect(find.text('Do the thing'), findsOneWidget);
    expect(find.text("Queued, I'll pick it up next"), findsOneWidget);
  });

  testWidgets('a Linux bot\'s chat mode sits behind + in the composer, beside pictures',
      (tester) async {
    final adapter = FakeAdapter((o) => switch (o.path) {
          '/api/bots/b1/chat' => FakeAdapter.json({'id': 't1', 'bot_id': 'b1'}),
          '/api/threads/t1/messages' => FakeAdapter.json(<Object>[]),
          '/api/bots/b1' => FakeAdapter.json({
              'id': 'b1',
              'name': 'Gogi',
              'computer': 'linux',
              'approval': {'mode': 'ask', 'ask_topics': ['browsing']},
            }),
          _ => FakeAdapter.json({}),
        });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chat-mode-pill')), findsNothing);
    expect(find.text('Ask Gogi'), findsOneWidget);
    await tester.tap(find.byKey(const Key('composer-plus')));
    await tester.pumpAndSettle();
    expect(find.text('Photo'), findsOneWidget);
    await tester.tap(find.byKey(const Key('attach-computer')));
    await tester.pumpAndSettle();
    expect(find.text('How Gogi uses its computer'), findsOneWidget);
    expect(
        find.descendant(
            of: find.byKey(const Key('chat-mode-askMe')),
            matching: find.byIcon(Icons.check)),
        findsOneWidget);
  });
}
