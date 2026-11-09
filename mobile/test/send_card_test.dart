import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/chat/cards/approval_answers.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

// The Send card (owner, 2026-11-03): every box the bot typed, then Send · Don't send · Change it….
const _letter =
    'Hi! I have built REST APIs in Node.js for six years.\nI can start this week.';

Map<String, dynamic> _sendCard({bool fromWeb = false}) => {
  'id': 's1',
  'kind': 'ask',
  'state': 'open',
  'tainted': true,
  'session_offer': false,
  'send': true,
  'from_web': fromWeb,
  'steps': [
    {
      'tool': 'click',
      'topic': 'browsing',
      'title': 'Send message',
      'detail': '',
      'floor': 'commit_click',
      'tainted_basis': false,
      'session_offer': false,
      'rows': [
        {
          'key': 'site',
          'label': 'Site',
          'value': 'www.upwork.com',
          'truncated': false,
        },
        {
          'key': 'draft',
          'label': 'Cover letter',
          'value': _letter,
          'truncated': false,
        },
        {
          'key': 'draft_2',
          'label': 'Amount',
          'value': '1500',
          'truncated': false,
        },
      ],
      'diff': null,
    },
  ],
};

FakeHandler _handler(
  Map<String, dynamic> card,
  Object expected,
  String closed,
) => (o) {
  if (o.method == 'GET') return FakeAdapter.json(card);
  expect(o.path, '/api/approvals/s1/answer');
  expect(o.data, expected);
  return FakeAdapter.json({...card, 'state': closed});
};

const _message = '{"card_id":"s1","kind":"ask","steps":["Send message"]}';

void main() {
  testWidgets(
    'the Send card shows every box and its three buttons, no web chip for own text',
    (tester) async {
      await pumpCard(
        tester,
        cardMessage('approval', _message),
        _handler(_sendCard(), const {}, 'open'),
      );
      expect(find.text('Cover letter'), findsOneWidget);
      expect(find.textContaining('I can start this week'), findsOneWidget);
      expect(find.text('Amount'), findsOneWidget);
      for (final label in ['Send', "Don't send", 'Change it…']) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('Yes'), findsNothing);
      expect(find.byKey(const Key('web-mark')), findsNothing);
    },
  );

  testWidgets('a Send card whose text came from a page keeps the web chip', (
    tester,
  ) async {
    await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler(_sendCard(fromWeb: true), const {}, 'open'),
    );
    expect(find.byKey(const Key('web-mark')), findsOneWidget);
  });

  testWidgets("Don't send answers no", (tester) async {
    final adapter = await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler(_sendCard(), {'answer': 'no'}, 'declined'),
    );
    await tester.tap(find.text("Don't send"));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST'), hasLength(1));
  });

  testWidgets('Change it asks what to say instead and sends it as an edit', (
    tester,
  ) async {
    final adapter = await pumpCard(
      tester,
      cardMessage('approval', _message),
      _handler(_sendCard(), {
        'answer': 'edit',
        'text': 'Say I start Monday',
      }, 'edited'),
    );
    await tester.tap(find.text('Change it…'));
    await tester.pumpAndSettle();
    expect(find.text('What should it say instead?'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Say I start Monday');
    await tester.tap(find.text('Send change'));
    await tester.pumpAndSettle();
    expect(adapter.requests.where((r) => r.method == 'POST'), hasLength(1));
  });

  test('a closed Send card says what you chose', () {
    final card = _sendCard();
    expect(closedLine({...card, 'state': 'approved'}), 'Sent: Send message');
    expect(
      closedLine({...card, 'state': 'declined'}),
      'Not sent: Send message',
    );
    expect(
      closedLine({...card, 'state': 'edited'}),
      'You asked for a change: Send message',
    );
    expect(
      closedLine({...card, 'send': false, 'state': 'approved'}),
      'Yes: Send message',
    );
  });
}
