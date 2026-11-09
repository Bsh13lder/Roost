import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/chat/cards/card_router.dart';

import '../fake_adapter.dart';

const _body =
    '{"card_id":"s1","bot_id":"b1","reason":"sign_in","host":"wizzair.com","url":"https://wizzair.com/","sign_in":true,"line":"Sign in"}';

Message _card() => Message(
      id: 'm-stuck',
      threadId: 't1',
      role: 'bot',
      body: _body,
      seq: 3,
      createdAt: '2026-11-05T12:00:00+00:00',
      kind: 'stuck',
    );

Future<FakeAdapter> _pump(WidgetTester tester, String? field) async {
  final adapter = FakeAdapter((o) => FakeAdapter.json({
        'id': 's1',
        'state': 'open',
        'bot_id': 'b1',
        'sign_in': true,
        'secret_field': field,
      }));
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: cardFor(_card())))),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  for (final kind in ['password', 'code']) {
    testWidgets('a Sign-in card that asks for your $kind shows a masked field that sends it',
        (tester) async {
      final adapter = await _pump(tester, kind);
      expect(find.textContaining('Type your wizzair.com $kind'), findsOneWidget);
      final field = tester.widget<TextField>(find.byKey(const Key('secret-field')));
      expect(field.obscureText, isTrue);
      await tester.enterText(find.byKey(const Key('secret-field')), '123456');
      await tester.pump();
      await tester.tap(find.text('Send'));
      await tester.pumpAndSettle();
      final sent = adapter.requests.where((r) => r.uri.path == '/api/stuck/s1/secret').single;
      expect(sent.data, kind == 'password' ? {'value': '123456', 'save': true} : {'value': '123456'});
      expect(tester.widget<TextField>(find.byKey(const Key('secret-field'))).controller?.text, isEmpty);
    });
  }

  testWidgets('Save in Vault shows only for a password, on by default', (tester) async {
    await _pump(tester, 'code');
    expect(find.byKey(const Key('secret-save')), findsNothing);
  });

  testWidgets('unticking Save in Vault sends save false', (tester) async {
    final adapter = await _pump(tester, 'password');
    final box = tester.widget<CheckboxListTile>(find.byKey(const Key('secret-save')));
    expect(box.value, isTrue);
    expect(find.text('Save in Vault'), findsOneWidget);
    await tester.tap(find.byKey(const Key('secret-save')));
    await tester.enterText(find.byKey(const Key('secret-field')), 'pw-1');
    await tester.pump();
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    final sent = adapter.requests.where((r) => r.uri.path == '/api/stuck/s1/secret').single;
    expect(sent.data, {'value': 'pw-1', 'save': false});
  });

  testWidgets('a Sign-in card with no field keeps Take control only', (tester) async {
    await _pump(tester, null);
    expect(find.byKey(const Key('secret-field')), findsNothing);
    expect(find.text('Take control'), findsOneWidget);
  });
}
