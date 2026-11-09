import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/app_version.dart';
import 'package:roost_mobile/features/settings/settings_screen.dart';
import 'package:roost_mobile/theme/accent.dart';
import 'package:roost_mobile/theme/app_theme.dart';
import 'package:roost_mobile/theme/tokens.dart';

import '../fake_adapter.dart';

Future<ProviderContainer> pumpSettings(
    WidgetTester tester, MemorySessionStore store, FakeAdapter adapter) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(store),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 2;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: Consumer(
      builder: (_, ref, _) => MaterialApp(
        theme: buildTheme(ref.watch(accentProvider)),
        home: const SettingsScreen(),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return container;
}

MemorySessionStore signedIn() => MemorySessionStore()
  ..url = 'http://127.0.0.1:18800'
  ..token = 'tok';

FakeAdapter quiet() => FakeAdapter((_) => FakeAdapter.json({}));

void main() {
  test('six accent choices, the first is the default violet', () {
    expect(Tokens.accents, hasLength(6));
    expect(Tokens.accents.first.accent, Tokens.accent);
    expect(Tokens.accents.map((a) => a.id).toSet(), hasLength(6));
  });

  test('the version shown matches pubspec.yaml', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    final line = RegExp(r'^version:\s*(\S+)', multiLine: true)
        .firstMatch(pubspec)!
        .group(1);
    expect(appVersion, line);
  });

  testWidgets('picking an accent applies it at once and keeps it on the phone',
      (tester) async {
    final store = signedIn();
    final c = await pumpSettings(tester, store, quiet());
    final pick = Tokens.accents[2];
    await tester.tap(find.byKey(Key('accent-${pick.id}')));
    await tester.pumpAndSettle();
    expect(c.read(accentProvider).id, pick.id);
    expect(store.accent, pick.id);
    final element = tester.element(find.byType(SettingsScreen));
    expect(Theme.of(element).colorScheme.primary, pick.accent);
    expect(AccentColors.of(element).strong, pick.strong);
  });

  testWidgets('a saved accent is read back when the app starts',
      (tester) async {
    final store = signedIn()..accent = Tokens.accents[4].id;
    final c = await pumpSettings(tester, store, quiet());
    expect(c.read(accentProvider).id, Tokens.accents[4].id);
  });

  testWidgets('an http address that is not this phone is refused',
      (tester) async {
    final store = signedIn();
    final c = await pumpSettings(tester, store, quiet());
    await tester.enterText(
        find.byKey(const Key('settings-gateway')), 'http://mac.ts.net');
    await tester.tap(find.byKey(const Key('save-gateway')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('gateway-error')), findsOneWidget);
    expect(c.read(authProvider).signedIn, isTrue);
    expect(store.url, 'http://127.0.0.1:18800');
  });

  testWidgets('saving a new address signs out and keeps the new address',
      (tester) async {
    final store = signedIn();
    final adapter = quiet();
    final c = await pumpSettings(tester, store, adapter);
    await tester.enterText(find.byKey(const Key('settings-gateway')),
        'mac.tail1234.ts.net');
    await tester.tap(find.byKey(const Key('save-gateway')));
    await tester.pumpAndSettle();
    final auth = c.read(authProvider);
    expect(auth.signedIn, isFalse);
    expect(auth.baseUrl, 'https://mac.tail1234.ts.net');
    expect(store.url, 'https://mac.tail1234.ts.net');
    expect(store.token, isNull);
    final logout = adapter.requests.where((r) => r.path.endsWith('/logout'));
    expect(logout.single.uri.toString(),
        'http://127.0.0.1:18800/api/auth/logout');
  });

  testWidgets('Sign out and the version are on the screen', (tester) async {
    final store = signedIn();
    final c = await pumpSettings(tester, store, quiet());
    await tester.dragUntilVisible(find.text('Version $appVersion'),
        find.byType(ListView), const Offset(0, -100));
    expect(find.text('Version $appVersion'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('settings-sign-out')));
    await tester.tap(find.byKey(const Key('settings-sign-out')));
    await tester.pumpAndSettle();
    expect(c.read(authProvider).signedIn, isFalse);
  });
}
