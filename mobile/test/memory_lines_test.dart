import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/profile/folds/memory_fold.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

const _offer =
    '{"text":"Remind me 2 hours before","kind":"preference","importance":5,"memory_id":null}';

void main() {
  testWidgets('a Not remembered line saves with Remember it', (tester) async {
    final adapter = await pumpCard(tester, cardMessage('memory_offer', _offer),
        (o) {
      expect(o.method, 'POST');
      expect(o.path, '/api/threads/t1/messages/m-memory_offer/remember');
      return FakeAdapter.json({
        'message': {},
        'memory': {'id': 'mem1', 'text': 'Remind me 2 hours before'},
      });
    });
    expect(find.textContaining('Not remembered: Remind me 2 hours before'),
        findsOneWidget);
    await tester.tap(find.text('Remember it'));
    await tester.pumpAndSettle();
    expect(adapter.requests, hasLength(1));
    expect(find.text('Remembered: Remind me 2 hours before'), findsOneWidget);
    expect(find.text('Remember it'), findsNothing);
  });

  testWidgets('an offer already saved reads Remembered', (tester) async {
    await pumpCard(
        tester,
        cardMessage('memory_offer',
            _offer.replaceFirst('"memory_id":null', '"memory_id":"mem1"')),
        (o) => FakeAdapter.json({}));
    expect(find.text('Remembered: Remind me 2 hours before'), findsOneWidget);
    expect(find.text('Remember it'), findsNothing);
  });

  testWidgets('What I remember edits a memory\'s words', (tester) async {
    var text = 'Remind me 1 hour before';
    final patches = <Object?>[];
    final adapter = FakeAdapter((o) {
      if (o.method == 'PATCH') {
        expect(o.path, '/api/memories/mem1');
        patches.add(o.data);
        text = (o.data as Map)['text'] as String;
        return FakeAdapter.json({'id': 'mem1', 'text': text});
      }
      return FakeAdapter.json([
        {'id': 'mem1', 'text': text, 'kind': 'preference', 'bot_id': 'b1',
         'updated_at': '2026-10-25T12:00:00+00:00'},
      ]);
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(
          home: Scaffold(
              body: SingleChildScrollView(child: MemoryFold(botId: 'b1')))),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Remind me 2 hours before');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(patches, [
      {'text': 'Remind me 2 hours before'}
    ]);
    expect(find.text('Remind me 2 hours before'), findsOneWidget);
  });
}
