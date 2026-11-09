import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/chat/cards/card_router.dart';
import 'package:roost_mobile/chat/mentions.dart';

import 'fake_adapter.dart';

Message cardMessage(String kind, String body) => Message(
      id: 'm-$kind',
      threadId: 't1',
      role: 'bot',
      body: body,
      seq: 3,
      createdAt: '2026-10-22T12:19:00+00:00',
      kind: kind,
    );

Future<FakeAdapter> pumpCard(
    WidgetTester tester, Message m, FakeHandler handler) async {
  final adapter = FakeAdapter(handler);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: cardFor(m)))),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  testWidgets('an options card sends the picked option and shrinks to it',
      (tester) async {
    final open = {
      'id': 'c1',
      'kind': 'ask',
      'state': 'open',
      'tainted': false,
      'session_offer': false,
      'steps': [],
      'choice': {
        'question': 'Which day?',
        'options': ['Monday', 'Tuesday'],
        'safe': 0,
        'own': false,
        'why': '',
      },
    };
    final adapter = await pumpCard(
      tester,
      cardMessage('approval', '{"card_id":"c1","kind":"ask","steps":[]}'),
      (o) {
        if (o.method == 'GET') return FakeAdapter.json(open);
        expect(o.path, '/api/approvals/c1/answer');
        expect(o.data, {'answer': 'pick', 'choice': 1});
        return FakeAdapter.json({...open, 'state': 'approved'});
      },
    );
    expect(find.text('Which day?'), findsOneWidget);
    expect(find.textContaining('Monday'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);

    await tester.tap(find.text('Tuesday'));
    await tester.pumpAndSettle();

    expect(adapter.requests.where((r) => r.method == 'POST'), hasLength(1));
    expect(find.text('✓ You answered: Tuesday'), findsOneWidget);
    expect(find.text('Dismiss'), findsNothing);
  });

  testWidgets('an Open card for a new site says Open, and Open answers yes',
      (tester) async {
    final open = {
      'id': 'c2',
      'kind': 'ask',
      'state': 'open',
      'tainted': true,
      'session_offer': false,
      'steps': [
        {
          'tool': 'open_page',
          'topic': null,
          'title': 'Open web.whatsapp.com',
          'detail': '',
          'floor': 'new_site',
          'tainted_basis': false,
          'session_offer': false,
          'rows': [
            {'key': 'url', 'label': 'Address', 'value': 'https://web.whatsapp.com/', 'truncated': false},
          ],
          'diff': null,
        },
      ],
    };
    final adapter = await pumpCard(
      tester,
      cardMessage('approval', '{"card_id":"c2","kind":"ask","steps":["Open web.whatsapp.com"]}'),
      (o) {
        if (o.method == 'GET') return FakeAdapter.json(open);
        expect(o.path, '/api/approvals/c2/answer');
        expect(o.data, {'answer': 'yes'});
        return FakeAdapter.json({...open, 'state': 'approved'});
      },
    );
    expect(find.text('Yes'), findsNothing);
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST'), hasLength(1));
  });

  testWidgets('the Add a key card clears the key and never echoes it',
      (tester) async {
    const secret = 'sk-live-very-secret-123';
    final request = {
      'id': 'r1',
      'state': 'open',
      'service': 'Stripe',
      'host': 'api.stripe.com',
      'why': 'To read invoices',
      'tainted': false,
    };
    final adapter = await pumpCard(
      tester,
      cardMessage('connector_request', '{"request_id":"r1"}'),
      (o) {
        if (o.method == 'GET') return FakeAdapter.json(request);
        expect(o.path, '/api/connector-requests/r1/save');
        expect(o.data, {'secret': secret});
        return FakeAdapter.json({...request, 'state': 'saved'});
      },
    );
    final field = tester.widget<TextField>(find.byKey(const Key('key-field')));
    expect(field.obscureText, isTrue);

    await tester.enterText(find.byKey(const Key('key-field')), secret);
    await tester.tap(find.text('Save'));
    await tester.pump();
    // Cleared the moment Save is pressed, before the call even returns.
    expect(
        tester
            .widget<TextField>(find.byKey(const Key('key-field')))
            .controller!
            .text,
        isEmpty);
    await tester.pumpAndSettle();

    expect(adapter.requests.where((r) => r.method == 'POST'), hasLength(1));
    expect(find.textContaining(secret), findsNothing);
    expect(find.text('Key added · Stripe'), findsOneWidget);
  });

  test('@mentions match only at a word start', () {
    const bots = [MentionOption('1', 'Scout'), MentionOption('2', 'Sage')];
    expect(matchingOptions(mentionQuery('hi @S'), bots), hasLength(2));
    expect(matchingOptions(mentionQuery('hi @Sc'), bots).single.name, 'Scout');
    expect(mentionQuery('me@scout'), isNull);
    expect(insertMention('hi @Sc', 6, 'Scout').text, 'hi @Scout ');
  });

  testWidgets('a Sign-in card is calm, and Take control uses open-sign-in',
      (tester) async {
    final posts = <String>[];
    final adapter = FakeAdapter((o) {
      if (o.method == 'POST') posts.add(o.path);
      if (o.path == '/api/stuck/s1') {
        return FakeAdapter.json(
            {'id': 's1', 'state': 'open', 'sign_in': true, 'bot_id': 'b1'});
      }
      if (o.path == '/api/bots/b1/control') {
        return FakeAdapter.json({'held': true});
      }
      return FakeAdapter.json({'state': 'open'});
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    final m = cardMessage('stuck',
        '{"card_id":"s1","bot_id":"b1","host":"upwork.com","url":"https://upwork.com/login","line":"Sign in","sign_in":true}');
    final router = GoRouter(routes: [
      GoRoute(
          path: '/',
          builder: (_, _) => Scaffold(body: cardFor(m)!)),
      GoRoute(path: '/computer/:id', builder: (_, _) => const Text('screen')),
    ]);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(routerConfig: router)));
    await tester.pumpAndSettle();
    expect(find.text('Waiting for you to sign in on upwork.com'),
        findsOneWidget);
    expect(find.text('Later'), findsOneWidget);
    expect(find.text('Check again'), findsOneWidget);
    await tester.tap(find.text('Take control'));
    await tester.pumpAndSettle();
    expect(posts, ['/api/stuck/s1/open-sign-in']);
    expect(find.text('screen'), findsOneWidget);
  });
}
