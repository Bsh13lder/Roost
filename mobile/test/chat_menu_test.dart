import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'fake_adapter.dart';

class _SeededLive extends LiveController {
  _SeededLive(this.primary);
  final bool primary;

  @override
  LiveState build() => LiveState(bots: {
        'b1': Bot.fromJson({
          'id': 'b1',
          'name': 'Gogi',
          'status': 'resting',
          'is_primary': primary,
        }),
      });
}

Future<FakeAdapter> pumpChat(WidgetTester tester, {bool primary = false}) async {
  final adapter = FakeAdapter((o) => switch (o.path) {
        '/api/threads/t1/fresh-start' => FakeAdapter.json({
            'id': 'f1', 'thread_id': 't1', 'role': 'system', 'kind': 'fresh_start', 'seq': 9,
            'created_at': '2026-10-25T21:30:00+00:00',
            'body': 'Fresh start: earlier web content is hidden from me.'}),
        '/api/bots/b1/chat' => FakeAdapter.json({'id': 't1', 'bot_id': 'b1'}),
        '/api/threads/t1/messages' => FakeAdapter.json([]),
        _ => FakeAdapter.json({}),
      });
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    liveProvider.overrideWith(() => _SeededLive(primary)),
  ]);
  addTearDown(container.dispose);
  final router = GoRouter(initialLocation: '/chat/b1', routes: [
    GoRoute(path: '/', builder: (_, _) => const Text('home')),
    GoRoute(
        path: '/chat/:id',
        builder: (_, s) => ChatScreen(botId: s.pathParameters['id']!)),
    GoRoute(
        path: '/profile/:id',
        builder: (_, s) => Text('profile ${s.pathParameters['id']}')),
  ]);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  testWidgets('the ⋯ menu has View profile, Find in chat, Share, Retire',
      (tester) async {
    await pumpChat(tester);
    await tester.tap(find.byKey(const Key('chat-menu')));
    await tester.pumpAndSettle();
    for (final label in [
      'View profile',
      'Find in chat',
      'Share as Template',
      'Retire this bot',
    ]) {
      expect(find.text(label), findsOneWidget);
    }
  });

  testWidgets('Fresh start posts the line', (tester) async {
    final adapter = await pumpChat(tester);
    await tester.tap(find.byKey(const Key('chat-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fresh start'));
    await tester.pumpAndSettle();
    expect(
        adapter.requests
            .where((r) => r.path.endsWith('/fresh-start'))
            .map((r) => r.method),
        ['POST']);
  });

  testWidgets('the main bot cannot be retired from the menu', (tester) async {
    await pumpChat(tester, primary: true);
    await tester.tap(find.byKey(const Key('chat-menu')));
    await tester.pumpAndSettle();
    expect(find.text('Retire this bot'), findsNothing);
  });

  testWidgets('View profile opens the profile', (tester) async {
    await pumpChat(tester);
    await tester.tap(find.byKey(const Key('chat-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('View profile'));
    await tester.pumpAndSettle();
    expect(find.text('profile b1'), findsOneWidget);
  });

  testWidgets('Retire asks first, then deletes and goes Home', (tester) async {
    final adapter = await pumpChat(tester);
    await tester.tap(find.byKey(const Key('chat-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retire this bot'));
    await tester.pumpAndSettle();
    expect(find.text('Retire Gogi?'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Retire this bot'));
    await tester.pumpAndSettle();
    expect(
        adapter.requests.where((r) => r.method == 'DELETE' && r.path == '/api/bots/b1'),
        hasLength(1));
    expect(find.text('home'), findsOneWidget);
  });
}
