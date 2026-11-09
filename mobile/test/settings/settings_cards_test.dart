import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/settings/mac_folders_screen.dart';
import 'package:roost_mobile/features/settings/notifications_screen.dart';
import 'package:roost_mobile/features/settings/settings_screen.dart';
import 'package:roost_mobile/theme/app_theme.dart';

import '../fake_adapter.dart';

FakeAdapter account() => FakeAdapter((o) => switch (o.uri.path) {
      '/api/auth/me' => FakeAdapter.json({'id': '1', 'username': 'Lisa Bird'}),
      '/api/mac/grants' => FakeAdapter.json([
          {'id': 'g1', 'label': 'Notes', 'path': '/x', 'access': 'read'},
          {'id': 'g2', 'label': 'Work', 'path': '/y', 'access': 'write'},
        ]),
      '/api/bots' => FakeAdapter.json([
          {'id': 'b1', 'name': 'Gogi', 'notify': true},
          {'id': 'b2', 'name': 'Proton', 'notify': false},
        ]),
      '/api/bots/b2/notify' =>
        FakeAdapter.json({'id': 'b2', 'name': 'Proton', 'notify': true}),
      _ => FakeAdapter.json({}),
    });

Future<void> pump(WidgetTester tester, FakeAdapter adapter) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()
      ..url = 'http://127.0.0.1:18800'
      ..token = 'tok'),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  final router = GoRouter(routes: [
    GoRoute(path: '/', builder: (_, _) => const SettingsScreen()),
    GoRoute(path: '/connectors', builder: (_, _) => const Text('connectors')),
    GoRoute(path: '/vault-passwords', builder: (_, _) => const Text('vault passwords')),
    GoRoute(path: '/mac-folders', builder: (_, _) => const MacFoldersScreen()),
    GoRoute(
        path: '/notifications',
        builder: (_, _) => const NotificationsScreen()),
  ]);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(theme: buildTheme(), routerConfig: router),
  ));
  await tester.pumpAndSettle();
}

Future<void> scrollTo(WidgetTester tester, String text) =>
    tester.scrollUntilVisible(find.text(text), 100,
        scrollable: find.byType(Scrollable).first);

void main() {
  testWidgets('Settings is grouped cards: account, connections, appearance…',
      (tester) async {
    await pump(tester, account());
    expect(find.text('Lisa Bird'), findsOneWidget);
    expect(find.text('LB'), findsOneWidget);
    for (final label in [
      'Connections',
      'Connectors',
      'Your Mac: folders',
      '2 folders',
      'Appearance',
      'Notifications',
      '1 of 2 bots',
      'Gateway',
    ]) {
      await scrollTo(tester, label);
      expect(find.text(label), findsWidgets);
    }
  });

  testWidgets('Notifications lists each bot with its own switch',
      (tester) async {
    final adapter = account();
    await pump(tester, adapter);
    await scrollTo(tester, '1 of 2 bots');
    await tester.tap(find.text('1 of 2 bots'));
    await tester.pumpAndSettle();
    expect(find.text('Gogi'), findsOneWidget);
    expect(find.text('Proton'), findsOneWidget);
    await tester.tap(find.byKey(const Key('notify-b2')));
    await tester.pumpAndSettle();
    final put = adapter.requests.where((r) => r.path == '/api/bots/b2/notify');
    expect(put.single.data, {'notify': true});
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('Your Mac: folders opens the list of every shared folder',
      (tester) async {
    await pump(tester, account());
    await scrollTo(tester, 'Your Mac: folders');
    await tester.tap(find.text('Your Mac: folders'));
    await tester.pumpAndSettle();
    expect(find.text('Notes'), findsOneWidget);
    expect(find.text('Work'), findsOneWidget);
  });

  testWidgets('Vault: passwords sits under Connections and opens its list',
      (tester) async {
    await pump(tester, account());
    await scrollTo(tester, 'Vault: passwords');
    await tester.tap(find.text('Vault: passwords'));
    await tester.pumpAndSettle();
    expect(find.text('vault passwords'), findsOneWidget);
  });
}
