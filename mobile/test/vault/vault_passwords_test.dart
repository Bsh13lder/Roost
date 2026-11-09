import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/vault/vault_models.dart';
import 'package:roost_mobile/vault/vault_passwords_screen.dart';

import '../fake_adapter.dart';

// Vault: passwords (owner, 2026-11-08): the list never holds a password, Add
// posts only to the Vault, a refusal shows the server's words, Always for this
// site PATCHes, Delete asks first.
const _row = {
  'id': 'v1',
  'host': 'upwork.com',
  'username': 'ana@example.com',
  'always': false,
  'created_at': '2026-11-01T10:00:00+00:00',
  'updated_at': '2026-11-01T10:00:00+00:00',
  'last_used_at': '2026-11-07T08:30:00+00:00',
};

Future<FakeAdapter> _pump(WidgetTester tester, FakeHandler handler) async {
  final adapter = FakeAdapter(handler);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: VaultPasswordsScreen()),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

Iterable<Object?> _sent(FakeAdapter a, String method) =>
    a.requests.where((r) => r.method == method).map((r) => r.data);

void main() {
  test('a saved login reads its row and has no password', () {
    final login = SavedLogin.fromJson({..._row, 'password': 'leak'});
    expect(login.host, 'upwork.com');
    expect(login.username, 'ana@example.com');
    expect(login.always, isFalse);
    expect(login.lastUsedAt, '2026-11-07T08:30:00+00:00');
    expect(login.toString(), isNot(contains('leak')));
  });

  testWidgets('the list shows the site, user name and last use, never a password',
      (tester) async {
    await _pump(tester, (o) => FakeAdapter.json([_row]));
    expect(find.text('upwork.com'), findsOneWidget);
    expect(find.textContaining('ana@example.com'), findsOneWidget);
    expect(find.textContaining('Last used Sat 7 Nov, 09:30'), findsOneWidget);
    expect(find.textContaining('Your bots never see them'), findsOneWidget);
    expect(find.textContaining('leak'), findsNothing);
  });

  testWidgets('an empty vault says how to add one', (tester) async {
    await _pump(tester, (o) => FakeAdapter.json(<Object>[]));
    expect(find.textContaining('No saved passwords'), findsOneWidget);
  });

  testWidgets('Always for this site PATCHes the login', (tester) async {
    final adapter = await _pump(tester, (o) {
      if (o.method == 'PATCH') {
        expect(o.path, '/api/vault/passwords/v1');
        return FakeAdapter.json({..._row, 'always': true});
      }
      return FakeAdapter.json([_row]);
    });
    await tester.tap(find.byKey(const Key('vault-always-v1')));
    await tester.pumpAndSettle();
    expect(_sent(adapter, 'PATCH'), [
      {'always': true}
    ]);
  });

  testWidgets('Delete asks first, then deletes', (tester) async {
    var gone = false;
    final adapter = await _pump(tester, (o) {
      if (o.method == 'DELETE') {
        gone = true;
        return FakeAdapter.json(null, status: 204);
      }
      return FakeAdapter.json(gone ? <Object>[] : [_row]);
    });
    await tester.tap(find.byKey(const Key('vault-delete-v1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Delete the upwork.com login'), findsOneWidget);
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'DELETE').single.path,
        '/api/vault/passwords/v1');
    expect(find.text('upwork.com'), findsNothing);
  });

  testWidgets('Add posts the site, user name and password, then clears it',
      (tester) async {
    var saved = false;
    final adapter = await _pump(tester, (o) {
      if (o.method == 'POST') {
        saved = true;
        return FakeAdapter.json(_row, status: 201);
      }
      return FakeAdapter.json(saved ? [_row] : <Object>[]);
    });
    await tester.tap(find.byKey(const Key('vault-add')));
    await tester.pumpAndSettle();
    final password = tester.widget<TextField>(find.byKey(const Key('vault-password')));
    expect(password.obscureText, isTrue);
    expect(password.autofillHints, [AutofillHints.newPassword]);
    await tester.enterText(find.byKey(const Key('vault-site')), ' upwork.com ');
    await tester.enterText(find.byKey(const Key('vault-username')), 'ana@example.com');
    await tester.enterText(find.byKey(const Key('vault-password')), 'hunter22');
    await tester.pump();
    await tester.tap(find.byKey(const Key('vault-save')));
    await tester.pumpAndSettle();
    final post = adapter.requests.where((r) => r.method == 'POST').single;
    expect(post.path, '/api/vault/passwords');
    expect(post.data,
        {'host': 'upwork.com', 'username': 'ana@example.com', 'password': 'hunter22'});
    expect(find.text('Saved in Vault: passwords'), findsOneWidget);
    expect(find.byKey(const Key('vault-password')), findsNothing);
    expect(find.text('upwork.com'), findsOneWidget);
  });

  testWidgets("a refusal shows the server's words and keeps the sheet open",
      (tester) async {
    await _pump(tester, (o) {
      if (o.method == 'POST') {
        return FakeAdapter.json(
            {'detail': "Those login details don't fit. Check the site, user name and password."},
            status: 422);
      }
      return FakeAdapter.json(<Object>[]);
    });
    await tester.tap(find.byKey(const Key('vault-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('vault-site')), 'not a site');
    await tester.enterText(find.byKey(const Key('vault-password')), 'hunter22');
    await tester.pump();
    await tester.tap(find.byKey(const Key('vault-save')));
    await tester.pumpAndSettle();
    expect(find.textContaining("Those login details don't fit"), findsOneWidget);
    expect(find.byKey(const Key('vault-save')), findsOneWidget);
    final field = tester.widget<TextField>(find.byKey(const Key('vault-password')));
    expect(field.controller?.text, isEmpty);
    expect(find.textContaining('hunter22'), findsNothing);
  });

  testWidgets('Save waits for a site and a password', (tester) async {
    final adapter = await _pump(tester, (o) => FakeAdapter.json(<Object>[]));
    await tester.tap(find.byKey(const Key('vault-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('vault-site')), 'upwork.com');
    await tester.tap(find.byKey(const Key('vault-save')));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST'), isEmpty);
  });
}
