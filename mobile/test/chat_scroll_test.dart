import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';

import 'chat_send_test.dart' show msg;
import 'fake_adapter.dart';

void main() {
  testWidgets('a long chat opens at the newest message; ↓ brings you back',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 800));
    final adapter = FakeAdapter((o) {
      if (o.path == '/api/bots/b1/chat') {
        return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
      }
      return FakeAdapter.json([
        for (var i = 1; i <= 60; i++)
          msg('m$i', i.isEven ? 'user' : 'bot', 'Message number $i', i),
      ]);
    });
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

    expect(find.text('Message number 60'), findsOneWidget);
    expect(find.text('Message number 1'), findsNothing);
    expect(find.byKey(const Key('jump-to-end')), findsNothing);

    await tester.drag(find.byType(ListView), const Offset(0, 1500));
    await tester.pumpAndSettle();
    expect(find.text('Message number 60'), findsNothing);
    expect(find.byKey(const Key('jump-to-end')), findsOneWidget);

    await tester.tap(find.byKey(const Key('jump-to-end')));
    await tester.pumpAndSettle();
    expect(find.text('Message number 60'), findsOneWidget);
    expect(find.byKey(const Key('jump-to-end')), findsNothing);
  });
}
