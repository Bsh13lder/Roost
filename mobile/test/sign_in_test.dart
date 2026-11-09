import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/auth/sign_in_screen.dart';

import 'fake_adapter.dart';

Future<ProviderContainer> pumpSignIn(
  WidgetTester tester,
  MemorySessionStore store,
  FakeAdapter adapter,
) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(store),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: SignInScreen()),
  ));
  await tester.pump();
  return container;
}

void main() {
  testWidgets('signing in keeps the cookie and the URL, never the password',
      (tester) async {
    final store = MemorySessionStore();
    final adapter = FakeAdapter((o) {
      expect(o.path, '/api/auth/login');
      expect(o.data, {'username': 'me', 'password': 'secret-pw'});
      return FakeAdapter.json(
        {'id': '1', 'username': 'me'},
        headers: {
          'set-cookie': ['roost_session=tok; HttpOnly'],
        },
      );
    });
    final container = await pumpSignIn(tester, store, adapter);

    await tester.enterText(
        find.byKey(const Key('gateway-url')), '127.0.0.1:18800/');
    await tester.enterText(find.byKey(const Key('username')), 'me');
    await tester.enterText(find.byKey(const Key('password')), 'secret-pw');
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();

    expect(container.read(authProvider).signedIn, isTrue);
    expect(store.token, 'tok');
    expect(store.url, 'http://127.0.0.1:18800');
    expect(adapter.requests.single.headers['Origin'], 'http://127.0.0.1:18800');
  });

  testWidgets('a wrong password shows a friendly message', (tester) async {
    final container = await pumpSignIn(
      tester,
      MemorySessionStore(),
      FakeAdapter((_) => FakeAdapter.json({'detail': 'no'}, status: 401)),
    );
    await tester.enterText(find.byKey(const Key('username')), 'me');
    await tester.enterText(find.byKey(const Key('password')), 'bad');
    await tester.tap(find.byKey(const Key('sign-in')));
    await tester.pumpAndSettle();
    expect(find.text('Wrong username or password.'), findsOneWidget);
    expect(container.read(authProvider).signedIn, isFalse);
  });

  testWidgets('the password can be shown to check what the keyboard typed',
      (tester) async {
    await pumpSignIn(tester, MemorySessionStore(), FakeAdapter((o) => FakeAdapter.json({})));
    TextField field() => tester.widget<TextField>(find.byKey(const Key('password')));
    expect(field().obscureText, isTrue);
    expect(field().autocorrect, isFalse);
    expect(field().enableSuggestions, isFalse);
    await tester.tap(find.byKey(const Key('show-password')));
    await tester.pump();
    expect(field().obscureText, isFalse);
  });
}
