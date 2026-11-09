import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/app.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/nav/main_back.dart';

import '../fake_adapter.dart';
import '../offline_test.dart' show homeAnswer;

FakeReply _answer(RequestOptions o) => switch (o.uri.path) {
      '/api/bots/main/chat' => FakeAdapter.json({'id': 't1'}),
      _ => homeAnswer(o),
    };

/// The main bot, with no events socket.
class _MainBot extends LiveController {
  @override
  LiveState build() => const LiveState(bots: {
        'main': Bot(
            id: 'main',
            name: 'Chief',
            avatar: Avatar(),
            status: BotStatus.resting,
            isPrimary: true),
      });
}

void main() {
  testWidgets("the app's screens send Back to Home",
      (tester) async {
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()
        ..url = 'http://127.0.0.1:18800'
        ..token = 'tok'),
      httpAdapterProvider.overrideWithValue(SwitchAdapter(_answer)),
      liveProvider.overrideWith(_MainBot.new),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const RoostApp()));
    await tester.pumpAndSettle();
    final router = container.read(routerProvider);
    String at() => router.routerDelegate.currentConfiguration.last.matchedLocation;

    for (final page in [
      '/board',
      '/settings',
      '/routines',
      '/skills',
      '/connectors',
      '/notifications',
      '/new-bot',
    ]) {
      router.go('/');
      await tester.pumpAndSettle();
      router.push(page);
      await tester.pumpAndSettle();
      expect(find.byType(MainBackScope), findsWidgets, reason: page);
      await tester.binding.handlePopRoute();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(at(), '/', reason: page);
    }
  });
}
