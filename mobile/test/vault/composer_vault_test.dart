import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';

import '../fake_adapter.dart';

// The chat's + menu has Save a password (owner, 2026-11-08): the same sheet as
// Settings, posted to Vault: passwords only, never to the chat.
FakeAdapter _server() => FakeAdapter((o) {
      if (o.path == '/api/bots/b1/chat') return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
      if (o.path == '/api/bots/b1') return FakeAdapter.json({'id': 'b1', 'name': 'Gela', 'computer': 'linux'});
      if (o.path == '/api/threads/t1/messages' && o.method == 'GET') return FakeAdapter.json(<Object>[]);
      if (o.path == '/api/vault/passwords' && o.method == 'POST') {
        return FakeAdapter.json({
          'id': 'v1',
          'host': 'upwork.com',
          'username': '',
          'always': false,
          'created_at': '2026-11-08T10:00:00+00:00',
          'updated_at': '2026-11-08T10:00:00+00:00',
          'last_used_at': null,
        }, status: 201);
      }
      return FakeAdapter.json({});
    });

void main() {
  testWidgets('Save a password in the + menu opens the sheet and posts only to the Vault',
      (tester) async {
    final adapter = _server();
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('composer-plus')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save a password'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('vault-password')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('vault-site')), 'upwork.com');
    await tester.enterText(find.byKey(const Key('vault-password')), 'hunter22');
    await tester.pump();
    await tester.tap(find.byKey(const Key('vault-save')));
    await tester.pumpAndSettle();

    final posts = adapter.requests
        .where((r) => r.method == 'POST' && r.path != '/api/bots/b1/chat')
        .map((r) => r.path);
    expect(posts, ['/api/vault/passwords']);
    expect(find.text('Saved in Vault: passwords'), findsOneWidget);
    expect(find.textContaining('hunter22'), findsNothing);
  });

  testWidgets('Cancel closes the sheet and sends nothing', (tester) async {
    final adapter = _server();
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('composer-plus')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save a password'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('vault-password')), 'hunter22');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('vault-password')), findsNothing);
    expect(adapter.requests.where((r) => r.method == 'POST' && r.path != '/api/bots/b1/chat'),
        isEmpty);
  });
}
