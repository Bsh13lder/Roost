import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/account_zone.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/task_dates.dart';
import 'package:roost_mobile/features/settings/settings_screen.dart';
import 'package:roost_mobile/theme/app_theme.dart';
import 'package:roost_mobile/util/app_time.dart';

import '../fake_adapter.dart';

FakeAdapter me(Object? zone) => FakeAdapter((o) => switch (o.uri.path) {
      '/api/auth/me' =>
        FakeAdapter.json({'id': '1', 'username': 'Lisa Bird', 'timezone': zone}),
      '/api/mac/grants' => FakeAdapter.json([]),
      '/api/bots' => FakeAdapter.json([]),
      _ => FakeAdapter.json({}),
    });

MemorySessionStore signedIn({String? zone}) => MemorySessionStore()
  ..url = 'http://127.0.0.1:18800'
  ..token = 'tok'
  ..timezone = zone;

ProviderContainer containerFor(MemorySessionStore store, FakeAdapter adapter) {
  final c = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(store),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(c.dispose);
  return c;
}

Future<void> settle(ProviderContainer c) async {
  c.read(authProvider);
  for (var i = 0; i < 5; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  tearDown(() => setAppZone('Europe/Madrid'));

  test("the zone from /api/auth/me is the app's zone, and it is kept", () async {
    final store = signedIn();
    final c = containerFor(store, me('America/New_York'));
    await settle(c);
    expect(await c.read(accountZoneProvider.future), 'America/New_York');
    expect(appZoneName(), 'America/New_York');
    expect(store.timezone, 'America/New_York');
    // A due time now reads on New York's clock.
    expect(dueWords('2026-10-23T12:00:00+00:00', today: DateTime.utc(2026, 10, 23)),
        'Today 08:00');
  });

  test('a new sign-in asks /api/auth/me again for its zone', () async {
    var zone = 'America/New_York';
    final adapter = FakeAdapter((o) => FakeAdapter.json({'username': 'x', 'timezone': zone}));
    final store = signedIn();
    final c = containerFor(store, adapter);
    c.listen(accountZoneProvider, (_, _) {});
    await settle(c);
    expect(await c.read(accountZoneProvider.future), 'America/New_York');
    zone = 'Asia/Tokyo';
    await c.read(authProvider.notifier).expire();
    c.read(authProvider.notifier).setToken('tok2');
    expect(await c.read(accountZoneProvider.future), 'Asia/Tokyo');
    expect(store.timezone, 'Asia/Tokyo');
  });

  test('a null zone changes nothing and sends nothing', () async {
    final store = signedIn(zone: 'Asia/Tokyo');
    final adapter = me(null);
    final c = containerFor(store, adapter);
    await settle(c);
    expect(await c.read(accountZoneProvider.future), 'Asia/Tokyo');
    expect(store.timezone, 'Asia/Tokyo');
    expect(adapter.requests.where((r) => r.method != 'GET'), isEmpty);
  });

  test('an unknown zone from the server is ignored', () async {
    final store = signedIn(zone: 'Asia/Tokyo');
    final c = containerFor(store, me('Mars/Olympus'));
    await settle(c);
    expect(await c.read(accountZoneProvider.future), 'Asia/Tokyo');
    expect(store.timezone, 'Asia/Tokyo');
  });

  test('the kept zone is used at start, before Roost answers (offline)', () async {
    final store = signedIn(zone: 'America/Los_Angeles');
    final adapter = SwitchAdapter((_) => FakeAdapter.json({}), down: true);
    final c = containerFor(store, adapter);
    await settle(c);
    expect(c.read(authProvider).ready, isTrue);
    expect(appZoneName(), 'America/Los_Angeles');
    expect(appClock('2026-10-23T12:19:00Z'), '05:19');
  });

  testWidgets('Settings shows the time zone as a read-only row', (tester) async {
    final c = containerFor(signedIn(), me('America/New_York'));
    tester.view.physicalSize = const Size(1080, 3600);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: c,
      child: MaterialApp(theme: buildTheme(), home: const SettingsScreen()),
    ));
    await tester.pumpAndSettle();
    final row = find.byKey(const Key('settings-time-zone'));
    expect(row, findsOneWidget);
    expect(find.descendant(of: row, matching: find.text('Time zone')), findsOneWidget);
    expect(find.descendant(of: row, matching: find.text('New York')), findsOneWidget);
    expect(find.text('Change it in Roost on your computer.'), findsOneWidget);
    // Read only: no chevron, nothing to open.
    expect(find.descendant(of: row, matching: find.byIcon(Icons.chevron_right)),
        findsNothing);
  });
}
