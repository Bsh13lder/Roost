import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

// Owner, 2026-10-29: Chief's "Create this bot" card showed only "Open this on
// the web for now." on the phone.

final _body = jsonEncode({
  'name': 'Gigs',
  'job': 'Handles your Upwork and Fiverr.',
  'avatar': {'shape': 'cub', 'color': '#3b82f6', 'badge': 'none', 'screen': 'glow'},
});

Message _tainted(Message m) => Message(
    id: m.id, threadId: m.threadId, role: m.role, body: m.body, seq: m.seq,
    createdAt: m.createdAt, kind: m.kind, tainted: true);

void main() {
  testWidgets('Create this bot creates it and folds to one line', (tester) async {
    final adapter = await pumpCard(tester, _tainted(cardMessage('suggestion', _body)),
        (o) => FakeAdapter.json(o.method == 'POST' ? {'id': 'b9', 'name': 'Gigs'} : []));
    expect(find.text('Suggested bot: Gigs'), findsOneWidget);
    expect(find.text('Handles your Upwork and Fiverr.'), findsOneWidget);
    expect(find.text('This run read outside content.'), findsOneWidget);
    await tester.tap(find.text('Create this bot'));
    await tester.pumpAndSettle();
    final post = adapter.requests.where((r) => r.method == 'POST').single;
    expect(post.path, '/api/bots');
    final sent = (post.data is String ? jsonDecode(post.data as String) : post.data) as Map;
    expect(sent['name'], 'Gigs');
    expect(sent['job'], 'Handles your Upwork and Fiverr.');
    expect((sent['avatar'] as Map)['shape'], 'cub');
    expect(find.text('Created Gigs'), findsOneWidget);
    expect(find.text('Create this bot'), findsNothing);
  });

  testWidgets('a refused create says why and keeps the button', (tester) async {
    await pumpCard(tester, cardMessage('suggestion', _body),
        (o) => o.method == 'POST'
            ? FakeAdapter.json({'detail': 'A bot named Gigs already exists.'}, status: 409)
            : FakeAdapter.json([]));
    await tester.tap(find.text('Create this bot'));
    await tester.pumpAndSettle();
    expect(find.text('A bot named Gigs already exists.'), findsOneWidget);
    expect(find.text('Create this bot'), findsOneWidget);
  });

  testWidgets('an unreadable suggestion is a quiet line', (tester) async {
    await pumpCard(tester, cardMessage('suggestion', '{"name":3}'), (o) => FakeAdapter.json([]));
    expect(find.text('Create this bot'), findsNothing);
  });
}
