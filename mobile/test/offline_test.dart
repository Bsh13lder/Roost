import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/reachability.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/app.dart';
import 'package:roost_mobile/features/home/home_screen.dart';
import 'package:roost_mobile/features/offline/offline_screen.dart';
import 'package:roost_mobile/features/settings/settings_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'fake_adapter.dart';

/// No events socket in these tests.
class QuietLive extends LiveController {
  @override
  LiveState build() => const LiveState();
}

FakeReply homeAnswer(RequestOptions o) => switch (o.uri.path) {
      '/api/auth/me' => FakeAdapter.json({'id': '1', 'username': 'me'}),
      '/api/my-turn' => FakeAdapter.json({'rows': []}),
      '/api/auth/logout' => FakeAdapter.json({}),
      _ => FakeAdapter.json([]),
    };

Future<ProviderContainer> pumpApp(WidgetTester tester, SwitchAdapter adapter,
    {MemorySessionStore? store}) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(store ??
        (MemorySessionStore()
          ..url = 'http://127.0.0.1:18800'
          ..token = 'tok')),
    httpAdapterProvider.overrideWithValue(adapter),
    liveProvider.overrideWith(QuietLive.new),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const RoostApp(),
  ));
  await tester.pumpAndSettle();
  // A miss waits out the grace pause before the offline screen shows.
  await tester.pump(offlineGrace);
  await tester.pumpAndSettle();
  return container;
}

void main() {
  testWidgets('Home: initials open Settings, + is New bot, one bottom bar',
      (tester) async {
    await pumpApp(tester, SwitchAdapter(homeAnswer));
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(find.byKey(const Key('settings')), findsNothing);
    expect(find.byKey(const Key('board')), findsOneWidget);
    expect(find.byKey(const Key('search')), findsOneWidget);
    expect(find.byKey(const Key('new-bot')), findsOneWidget);
    await tester.tap(find.byKey(const Key('initials')));
    await tester.pumpAndSettle();
    expect(find.byType(SettingsScreen), findsOneWidget);
  });

  testWidgets('an unreachable gateway shows the calm offline screen',
      (tester) async {
    final adapter = SwitchAdapter(homeAnswer, down: true);
    await pumpApp(tester, adapter);
    expect(find.byType(OfflineScreen), findsOneWidget);
    expect(find.text("Can't reach your Roost"), findsOneWidget);
    expect(find.textContaining('Tailscale'), findsOneWidget);
    expect(find.byKey(const Key('offline-try-again')), findsOneWidget);
    expect(find.byKey(const Key('offline-settings')), findsOneWidget);
  });

  testWidgets('it retries every 15 s and returns to where you were',
      (tester) async {
    final adapter = SwitchAdapter(homeAnswer, down: true);
    await pumpApp(tester, adapter);
    expect(find.byType(OfflineScreen), findsOneWidget);
    final before = adapter.requests.length;

    await tester.pump(offlineRetryInterval);
    await tester.pumpAndSettle();
    expect(adapter.requests.length, greaterThan(before));
    expect(find.byType(OfflineScreen), findsOneWidget);

    adapter.down = false;
    await tester.pump(offlineRetryInterval);
    await tester.pumpAndSettle();
    expect(find.byType(OfflineScreen), findsNothing);
    expect(find.byType(HomeScreen), findsOneWidget);
  });

  testWidgets('Try again checks at once', (tester) async {
    final adapter = SwitchAdapter(homeAnswer, down: true);
    await pumpApp(tester, adapter);
    adapter.down = false;
    await tester.tap(find.byKey(const Key('offline-try-again')));
    await tester.pumpAndSettle();
    expect(find.byType(OfflineScreen), findsNothing);
  });

  testWidgets('one miss inside the grace pause is not offline',
      (tester) async {
    final adapter = SwitchAdapter(homeAnswer, down: true);
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()
        ..url = 'http://127.0.0.1:18800'
        ..token = 'tok'),
      httpAdapterProvider.overrideWithValue(adapter),
      liveProvider.overrideWith(QuietLive.new),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const RoostApp()));
    await tester.pumpAndSettle();
    expect(find.byType(OfflineScreen), findsNothing);   // still in the grace pause
    adapter.down = false;                               // the VPN came up
    await tester.pump(offlineGrace);
    await tester.pumpAndSettle();
    expect(find.byType(OfflineScreen), findsNothing);
    expect(find.byType(HomeScreen), findsOneWidget);
  });

  testWidgets('Settings opens from the offline screen', (tester) async {
    await pumpApp(tester, SwitchAdapter(homeAnswer, down: true));
    await tester.tap(find.byKey(const Key('offline-settings')));
    await tester.pumpAndSettle();
    expect(find.byType(SettingsScreen), findsOneWidget);
  });

  testWidgets('a 401 is not offline: it signs you out', (tester) async {
    final adapter =
        SwitchAdapter((_) => FakeAdapter.json({'detail': 'x'}, status: 401));
    final c = await pumpApp(tester, adapter);
    expect(find.byType(OfflineScreen), findsNothing);
    expect(c.read(authProvider).signedIn, isFalse);
    expect(c.read(offlineProvider), isFalse);
  });
}
