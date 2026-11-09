import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/computer/computer_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';

import '../fake_adapter.dart';
import '../fake_socket.dart';

/// The main bot and the computer's bot, with no events socket.
class _Bots extends LiveController {
  @override
  LiveState build() => const LiveState(bots: {
        'main': Bot(
            id: 'main',
            name: 'Chief',
            avatar: Avatar(),
            status: BotStatus.resting,
            isPrimary: true),
        'b1': Bot(
            id: 'b1', name: 'Scout', avatar: Avatar(), status: BotStatus.resting),
      });
}

void main() {
  testWidgets("Back from a computer you only watch opens its bot's chat",
      (tester) async {
    final router = GoRouter(routes: [
      GoRoute(path: '/', builder: (_, _) => const Text('home')),
      GoRoute(
          path: '/chat/:botId',
          builder: (_, s) => Text('chat ${s.pathParameters['botId']}')),
      GoRoute(
          path: '/computer/:botId',
          builder: (_, s) =>
              ComputerScreen(botId: s.pathParameters['botId']!)),
    ]);
    addTearDown(router.dispose);
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(FakeAdapter((o) {
        if (o.path == '/api/bots/b1/control') {
          return FakeAdapter.json({'held': false});
        }
        if (o.path == '/api/bots/b1/teach') {
          return FakeAdapter.json({'teaching': false});
        }
        if (o.path == '/api/stuck') return FakeAdapter.json([]);
        return FakeAdapter.json({});
      })),
      socketOpenerProvider.overrideWithValue((uri, headers) => FakeSocket()),
      liveProvider.overrideWith(_Bots.new),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(routerConfig: router),
    ));
    router.push('/chat/b1');
    router.push('/computer/b1');
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(find.byType(ComputerScreen), findsOneWidget);

    await tester.binding.handlePopRoute();
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('chat b1'), findsOneWidget);
    expect(router.routerDelegate.currentConfiguration.last.matchedLocation,
        '/chat/b1');
    await tester.pumpWidget(const SizedBox());
  });
}
