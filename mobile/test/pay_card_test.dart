import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/chat/cards/approval_answers.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

// The Pay card (owner, 2026-11-05): fields only for the card parts the page asks for; a saved card asks only the
// security code; Pay sends the card in the body, Don't pay answers no.
Map<String, dynamic> _payCard() => {
  'id': 'p1',
  'kind': 'ask',
  'state': 'open',
  'tainted': true,
  'session_offer': false,
  'pay': true,
  'steps': [
    {
      'tool': 'click',
      'topic': 'browsing',
      'title': "Click 'Pay 36 EUR'",
      'detail': '',
      'floor': 'commit_click',
      'tainted_basis': false,
      'session_offer': false,
      'rows': const [],
      'diff': null,
    },
  ],
};

const _message = '{"card_id":"p1","kind":"ask","steps":["Pay"]}';

FakeHandler _handler(Map<String, dynamic> fields, List<Object?> posted) => (o) {
  if (o.method == 'GET' && o.path.endsWith('/pay')) {
    return FakeAdapter.json(fields);
  }
  if (o.method == 'GET') return FakeAdapter.json(_payCard());
  posted.add(o.data);
  return FakeAdapter.json({..._payCard(), 'state': 'approved'});
};

void main() {
  testWidgets('a new card fills every part the page asks and Pay sends it', (
    tester,
  ) async {
    final posted = <Object?>[];
    await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler({
        'parts': ['number', 'exp', 'name', 'cvc'],
        'refusal': '',
        'cards': const [],
      }, posted),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('pay-number')),
      '4242424242424242',
    );
    await tester.enterText(find.byKey(const Key('pay-exp')), '12/28');
    await tester.enterText(find.byKey(const Key('pay-name')), 'Ana Garcia');
    await tester.enterText(find.byKey(const Key('pay-cvc')), '737');
    await tester.tap(find.byType(Checkbox));
    await tester.tap(find.text('Pay'));
    await tester.pumpAndSettle();
    expect(posted, [
      {
        'number': '4242424242424242',
        'exp': '12/28',
        'name': 'Ana Garcia',
        'cvc': '737',
        'save': true,
      },
    ]);
  });

  testWidgets('a saved card asks only the security code', (tester) async {
    final posted = <Object?>[];
    await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler({
        'parts': ['number', 'exp', 'cvc'],
        'refusal': '',
        'cards': [
          {'id': 'c1', 'brand': 'visa', 'last4': '4242', 'last_used_at': null},
        ],
      }, posted),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Visa ending 4242'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pay-number')), findsNothing);
    await tester.enterText(find.byKey(const Key('pay-cvc')), '737');
    await tester.tap(find.text('Pay'));
    await tester.pumpAndSettle();
    expect(posted, [
      {'card_id': 'c1', 'cvc': '737'},
    ]);
  });

  testWidgets('a protected card box says to take control', (tester) async {
    await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler({
        'parts': const [],
        'refusal': "This site's card box is protected.",
        'cards': const [],
      }, []),
    );
    await tester.pumpAndSettle();
    expect(find.text("This site's card box is protected."), findsOneWidget);
    expect(find.byKey(const Key('pay-number')), findsNothing);
  });

  test('a closed Pay card says paid or not paid', () {
    expect(
      closedLine({..._payCard(), 'state': 'approved'}),
      "You paid: Click 'Pay 36 EUR'",
    );
    expect(
      closedLine({..._payCard(), 'state': 'declined'}),
      "Not paid: Click 'Pay 36 EUR'",
    );
  });
}
