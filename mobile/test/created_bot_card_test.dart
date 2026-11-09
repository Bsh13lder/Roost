import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/chat/cards/created_bot_card.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

// Owner, 2026-10-29: the main bot's "Created …" card showed only "Open this on
// the web for now." on the phone; a bot made after web content says so.

String _body({bool checked = false}) => jsonEncode({
      'bot_id': 'b9',
      'name': 'Gigs',
      'job': 'Handles your Upwork and Fiverr.',
      'instructions': 'Check messages and draft replies.',
      'avatar': {'shape': 'cub', 'color': '#3b82f6', 'badge': 'none', 'screen': 'glow'},
      if (checked) 'checked': true,
    });

Message _card({bool checked = false}) => cardMessage('bot_created', _body(checked: checked));

void main() {
  testWidgets('shows the new bot with its instructions, Open and Undo', (tester) async {
    await pumpCard(tester, _card(), (o) => FakeAdapter.json([]));
    expect(find.text('Created Gigs'), findsOneWidget);
    expect(find.text('Handles your Upwork and Fiverr.'), findsOneWidget);
    expect(find.text('Check messages and draft replies.'), findsOneWidget);
    expect(find.text('Open'), findsOneWidget);
    expect(find.text('Undo'), findsOneWidget);
    expect(find.text(createdCheckedText), findsNothing);
  });

  testWidgets('a bot made after web content says it was auto-checked', (tester) async {
    await pumpCard(tester, _card(checked: true), (o) => FakeAdapter.json([]));
    expect(find.text(createdCheckedText), findsOneWidget);
  });

  testWidgets('Undo retires the bot after you confirm', (tester) async {
    final adapter = await pumpCard(tester, _card(), (o) => FakeAdapter.json({}));
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Retire this bot'));
    await tester.pumpAndSettle();
    final delete = adapter.requests.where((r) => r.method == 'DELETE').single;
    expect(delete.path, '/api/bots/b9');
    expect(find.text('Undone: Gigs was retired.'), findsOneWidget);
  });

  testWidgets('an unreadable card is a quiet line', (tester) async {
    await pumpCard(tester, cardMessage('bot_created', '{"name":1}'), (o) => FakeAdapter.json([]));
    expect(find.text('Undo'), findsNothing);
  });
}
