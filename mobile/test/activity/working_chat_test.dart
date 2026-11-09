import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../computer_card_test.dart' show Harness;

Map<String, dynamic> _message(String id, String body, int seq) => {
      'type': 'message',
      'thread_id': 't1',
      'message': {
        'id': id,
        'thread_id': 't1',
        'role': 'bot',
        'body': body,
        'seq': seq,
        'created_at': '2026-10-23T12:00:00Z',
        'kind': 'text',
        'author_bot_id': 'b1',
      },
    };

Map<String, dynamic> _delta(String id, String delta) =>
    {'type': 'text_delta', 'thread_id': 't1', 'message_id': id, 'delta': delta};

Finder _inChat(Finder f) => find.descendant(of: find.byType(ListView), matching: f);

// Owner, 2026-10-27: a working bot shows its own robot with what it is doing,
// never the words "On it".
void main() {
  testWidgets('a streamed lead is the working line beside the bot\'s robot, never a bubble', (tester) async {
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, _message('p1', '', 0));
    await h.frame(tester, _delta('p1', 'On it: checking your week.'));

    expect(_inChat(find.byKey(const Key('working-bot'))), findsOneWidget);
    expect(_inChat(find.text('Checking your week…')), findsOneWidget);
    expect(_inChat(find.textContaining('On it')), findsNothing);
    expect(_inChat(find.textContaining('checking your week.')), findsNothing);

    await h.frame(tester, _delta('p1', '\n\nYou have two meetings.'));
    expect(_inChat(find.text('You have two meetings.')), findsOneWidget);
    expect(_inChat(find.byKey(const Key('working-bot'))), findsNothing);
    expect(_inChat(find.textContaining('On it')), findsNothing);
  });

  testWidgets('a finished reply shows only its answer, and Copy copies what shows', (tester) async {
    final copied = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied.add((call.arguments as Map)['text'] as String);
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    final h = Harness();
    await h.pump(tester);
    await h.frame(tester, _message('m1', 'On it: x\n\nAnswer.', 2));
    await h.frame(tester, {'type': 'bot_status', 'bot_id': 'b1', 'status': 'resting'});

    expect(_inChat(find.text('Answer.')), findsOneWidget);
    expect(_inChat(find.textContaining('On it')), findsNothing);
    expect(_inChat(find.textContaining('x\n')), findsNothing);

    // The words are selectable; the reply's time line opens the long-press menu.
    await tester.longPress(_inChat(find.text('14:00')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Copy'));
    await tester.pumpAndSettle();
    expect(copied, ['Answer.']);
  });
}
