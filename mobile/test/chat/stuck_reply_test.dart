import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/chat/cards/card_router.dart';
import 'package:roost_mobile/chat/message_actions.dart';

import '../fake_adapter.dart';

const _body =
    '{"card_id":"s1","bot_id":"b1","reason":"challenge","host":"shop.example","url":"https://shop.example/x","note":"web words","line":"I\'m stuck"}';

Message _stuck({String body = _body}) => Message(
      id: 'm-stuck',
      threadId: 't1',
      role: 'bot',
      body: body,
      seq: 3,
      createdAt: '2026-11-02T12:00:00+00:00',
      kind: 'stuck',
    );

Future<void> _pump(WidgetTester tester, Message m, String state,
    {void Function(Message)? onReply}) async {
  final adapter = FakeAdapter((o) => FakeAdapter.json(
      {'id': 's1', 'state': state, 'bot_id': 'b1', 'sign_in': false}));
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
        home: Scaffold(
            body: SingleChildScrollView(child: cardFor(m, onReply: onReply)))),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Reply on an open Stuck card quotes it for your next message',
      (tester) async {
    Message? quoted;
    await _pump(tester, _stuck(), 'open', onReply: (m) => quoted = m);
    await tester.tap(find.text('Reply'));
    await tester.pumpAndSettle();
    expect(quoted?.id, 'm-stuck');
  });

  testWidgets('with nowhere to reply the card has no Reply', (tester) async {
    await _pump(tester, _stuck(), 'open');
    expect(find.text('Reply'), findsNothing);
  });

  testWidgets('a card you answered in the chat folds to its own line',
      (tester) async {
    await _pump(tester, _stuck(), 'replied', onReply: (_) {});
    expect(find.text('You answered in the chat'), findsOneWidget);
    expect(find.text('Reply'), findsNothing);
  });

  test('a Stuck card is quoted in fixed words, never its note', () {
    expect(quoteSource(_stuck()), 'Stuck on shop.example');
    expect(
        quoteSource(_stuck(
            body: '{"host":"shop.example","sign_in":true,"note":"x"}')),
        'Waiting for you to sign in to shop.example');
    expect(quoteSource(_stuck(body: '{"host":""}')), 'Needs your help');
    expect(
        quoteSource(Message(
            id: 'm1',
            threadId: 't1',
            role: 'bot',
            body: 'hello there',
            seq: 1,
            createdAt: '2026-11-02T12:00:00+00:00',
            kind: 'text')),
        'hello there');
  });
}
